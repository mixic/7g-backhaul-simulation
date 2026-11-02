/*
 * 7g-backhaul-simulation
 * Copyright (C) 2026 MILAN NIKOLIC
 *
 * This program is free software: you can redistribute it and/or modify
 * it under the terms of the GNU General Public License as published by
 * the Free Software Foundation, either version 3 of the License, or
 * (at your option) any later version.
 *
 * This program is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU General Public License for more details.
 *
 * You should have received a copy of the GNU General Public License
 * along with this program.  If not, see <https://www.gnu.org/licenses/>.
 */

/*
 * Role-fluid, kinematic backhaul fabric in ns-3 (see docs/kinematic-fabric.md).
 *
 *  - 50 nodes, no IPv4: every node speaks over PacketSockets, so the fabric
 *    owns forwarding end to end.
 *  - custom RoleFluidHeader: content name, hop limit, fragment offset, MTU and
 *    a send timestamp for per-hop delay measurement.
 *  - flood-learned FIB + PIT (no DNS), byte-offset fragmentation and
 *    reassembly with a per-path MTU, and a potential field
 *    Phi = a*queue + b*latency + g*fragment + d*role.
 *  - kinematic (Turbo) controller: EMA of request velocity/acceleration,
 *    impedance 1 + k1*P + k2*P^3, role transitions with inertia.
 *
 * Scenarios (each is one mode; the experiment runner compares paired modes):
 *   A_static   fixed roles, gradient, shockwave at t=50
 *   A_turbo    turbo controller, shockwave at t=50
 *   B_dns      role move with DNS (300 s TTL) name mapping
 *   B_name     role move with name-based forwarding and withdrawal
 *   C_single   single-path, MTU-driven fragmentation, no loss
 *   C_fabric   balancer splitting, MTU fragmentation, satellite loss
 *   stability  10 000 s at low rate (deadlock check)
 */

#include "ns3/applications-module.h"
#include "ns3/core-module.h"
#include "ns3/csma-module.h"
#include "ns3/error-model.h"
#include "ns3/network-module.h"
#include "ns3/packet-socket-address.h"
#include "ns3/packet-socket-factory.h"
#include "ns3/packet-socket-helper.h"
#include "ns3/point-to-point-module.h"

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <fstream>
#include <map>
#include <random>
#include <set>
#include <string>
#include <vector>

using namespace ns3;

namespace
{
constexpr uint32_t NODE_COUNT = 50;
constexpr uint32_t NAME_COUNT = 10;
constexpr uint32_t OBJECT_BYTES = 2048;
constexpr uint8_t KIND_HELLO = 1;
constexpr uint8_t KIND_INTEREST = 2;
constexpr uint8_t KIND_DATA = 3;
constexpr uint8_t KIND_WITHDRAW = 4;
constexpr uint32_t PIT_LIFETIME_MS = 15000;
constexpr uint32_t RTO_MS = 300;
constexpr uint8_t HELLO_TTL = 64;
constexpr uint32_t CACHE_OBJECTS = 8;
constexpr uint32_t FRAGMENTS_IN_OBJECT = 4;
constexpr double QUEUE_REFERENCE_MS = 20.0;
constexpr double MOVE_SECONDS = 50.0;
constexpr double DNS_TTL_SECONDS = 300.0;

enum Role
{
    ROLE_ROUTER = 0,
    ROLE_BALANCER = 1,
    ROLE_SERVER = 2
};

const char*
RoleName(int role)
{
    switch (role)
    {
    case ROLE_ROUTER:
        return "router";
    case ROLE_BALANCER:
        return "balancer";
    case ROLE_SERVER:
        return "server";
    default:
        return "?";
    }
}

class RoleFluidHeader : public Header
{
  public:
    static TypeId GetTypeId()
    {
        static TypeId tid = TypeId("RoleFluidHeader")
                                .SetParent<Header>()
                                .SetGroupName("Fabric")
                                .AddConstructor<RoleFluidHeader>();
        return tid;
    }

    TypeId GetInstanceTypeId() const override { return GetTypeId(); }
    uint32_t GetSerializedSize() const override { return 1 + 8 + 4 + 2 + 2 + 2 + 1 + 1 + 8 + 8; }

    void Serialize(Buffer::Iterator start) const override
    {
        Buffer::Iterator it = start;
        it.WriteU8(kind);
        it.WriteHtonU64(name);
        it.WriteHtonU32(seq);
        it.WriteHtonU16(offset);
        it.WriteHtonU16(total);
        it.WriteHtonU16(mtu);
        it.WriteU8(hopLimit);
        it.WriteU8(flags);
        uint64_t bits;
        std::memcpy(&bits, &sendTime, sizeof(bits));
        it.WriteHtonU64(bits);
        std::memcpy(&bits, &costAccum, sizeof(bits));
        it.WriteHtonU64(bits);
    }

    uint32_t Deserialize(Buffer::Iterator start) override
    {
        Buffer::Iterator it = start;
        kind = it.ReadU8();
        name = it.ReadNtohU64();
        seq = it.ReadNtohU32();
        offset = it.ReadNtohU16();
        total = it.ReadNtohU16();
        mtu = it.ReadNtohU16();
        hopLimit = it.ReadU8();
        flags = it.ReadU8();
        uint64_t bits = it.ReadNtohU64();
        std::memcpy(&sendTime, &bits, sizeof(bits));
        bits = it.ReadNtohU64();
        std::memcpy(&costAccum, &bits, sizeof(bits));
        return GetSerializedSize();
    }

    void Print(std::ostream& os) const override
    {
        os << "kind=" << int(kind) << " name=" << name << " offset=" << offset;
    }

    uint8_t kind{0};
    uint64_t name{0};
    uint32_t seq{0};
    uint16_t offset{0};
    uint16_t total{0};
    uint16_t mtu{1500};
    uint8_t hopLimit{0};
    uint8_t flags{0};
    double sendTime{0.0};
    double costAccum{0.0};
};

struct FibEntry
{
    uint32_t device;
    double latencyMs;
    uint16_t mtu;
};

class FabricNode : public Application
{
  public:
    static TypeId GetTypeId()
    {
        static TypeId tid = TypeId("FabricNode")
                                .SetParent<Application>()
                                .SetGroupName("Fabric")
                                .AddConstructor<FabricNode>();
        return tid;
    }

    uint32_t index{0};
    bool isServer{false};
    bool isClient{false};
    bool turbo{false};
    bool balancerMode{false};
    bool dnsMode{false};
    double requestRate{10.0};
    double shockwaveMultiplier{12.0};
    bool shockwaveEnabled{false};
    bool moveEnabled{false};
    bool lossEnabled{false};

    std::vector<double> deviceLatencyMs;
    std::vector<uint16_t> deviceMtu;

    std::map<uint64_t, std::vector<FibEntry>> fib;
    std::map<std::pair<uint64_t, uint32_t>, std::pair<uint32_t, double>> pit;
    std::map<uint64_t, std::map<uint16_t, std::string>> cache;
    std::map<uint64_t, uint16_t> cacheTotal;
    std::set<std::pair<uint64_t, uint32_t>> seenHello;
    std::map<uint64_t, double> bestCost;
    std::map<std::pair<uint64_t, uint32_t>, double> interestFirstSent;
    std::map<std::pair<uint64_t, uint32_t>, std::set<uint16_t>> receivedOffsets;
    std::map<std::pair<uint64_t, uint32_t>, uint32_t> retransmissions;
    std::map<uint64_t, uint32_t> frozenEgress; // DNS-cached egress per name
    std::map<uint64_t, uint32_t> latestHelloDevice;

    int role{ROLE_ROUTER};
    int pendingRole{-1};
    double pendingRoleAt{0.0};
    double roleInertiaMs{50.0};

    double emaVelocity{0.0};
    double emaAcceleration{0.0};
    double lastRate{0.0};
    double pressure{0.0};
    double lastControl{-1.0};

    uint64_t interestsSent{0};
    uint64_t interestsForwarded{0};
    uint64_t interestsUnresolved{0};
    uint64_t retransmissionsSent{0};
    uint64_t duplicates{0};
    uint64_t roleTransitions{0};
    uint64_t localServes{0};
    uint64_t completedObjects{0};
    uint64_t dataFragmentsSent{0};
    uint64_t objectsServed{0};
    double ttfbSumMs{0.0};
    uint64_t ttfbSamples{0};
    double queueDelaySumMs{0.0};
    uint64_t queueDelaySamples{0};
    double shockQueueSumMs{0.0};
    uint64_t shockQueueSamples{0};
    std::map<uint64_t, double> firstSuccessAfterMove;

    void ConfigureNode(uint32_t id,
                       bool server,
                       bool client,
                       bool turboFlag,
                       bool balancer,
                       bool dns,
                       double rate,
                       bool shockwave,
                       bool move,
                       bool loss)
    {
        index = id;
        isServer = server;
        isClient = client;
        turbo = turboFlag;
        balancerMode = balancer;
        dnsMode = dns;
        requestRate = rate;
        shockwaveEnabled = shockwave;
        moveEnabled = move;
        lossEnabled = loss;
        if (isServer)
        {
            role = ROLE_SERVER;
        }
        else if (balancer)
        {
            role = ROLE_BALANCER;
        }
    }

    uint64_t MyName() const { return static_cast<uint64_t>(index / 5); }

    bool Serves(uint64_t name, double now) const
    {
        if (!isServer)
        {
            return false;
        }
        if (name == 0 && moveEnabled)
        {
            // name 0 moves from server 0 to server 5 at MOVE_SECONDS.
            return (index == 0 && now < MOVE_SECONDS) || (index == 5 && now >= MOVE_SECONDS);
        }
        return MyName() == name;
    }

  private:
    void StartApplication() override
    {
        m_socket = Socket::CreateSocket(GetNode(), PacketSocketFactory::GetTypeId());
        m_socket->Bind();
        m_socket->SetRecvCallback(MakeCallback(&FabricNode::HandleRead, this));

        if (isServer)
        {
            Simulator::Schedule(Seconds(1.0 + 0.01 * index),
                                &FabricNode::Announce,
                                this,
                                MyName());
            if (moveEnabled && index == 0)
            {
                Simulator::Schedule(Seconds(MOVE_SECONDS), &FabricNode::Withdraw, this, 0u);
            }
            if (moveEnabled && index == 5)
            {
                Simulator::Schedule(Seconds(MOVE_SECONDS), &FabricNode::Announce, this, 0u);
            }
        }
        if (isClient)
        {
            ScheduleNextRequest();
        }
        Simulator::Schedule(MilliSeconds(200), &FabricNode::ControlTick, this);
    }

    void StopApplication() override
    {
        if (m_socket)
        {
            m_socket->Close();
        }
    }

    void SendOn(uint32_t device, Ptr<Packet> packet)
    {
        PacketSocketAddress address;
        address.SetSingleDevice(device);
        address.SetPhysicalAddress(Mac48Address::GetBroadcast());
        address.SetProtocol(0x0800);
        m_socket->SendTo(packet, 0, address);
    }

    void SendOnAll(Ptr<Packet> packet, int except = -1)
    {
        for (uint32_t device = 0; device < GetNode()->GetNDevices(); ++device)
        {
            if (static_cast<int>(device) == except)
            {
                continue;
            }
            SendOn(device, packet->Copy());
        }
    }

    static Ptr<Packet> MakePacket(const RoleFluidHeader& header)
    {
        Ptr<Packet> packet = Create<Packet>();
        packet->AddHeader(header);
        return packet;
    }

    void Announce(uint64_t name)
    {
        RoleFluidHeader header;
        header.kind = KIND_HELLO;
        header.name = name;
        header.seq = static_cast<uint32_t>(index);
        header.hopLimit = HELLO_TTL;
        header.sendTime = Simulator::Now().GetSeconds();
        SendOnAll(MakePacket(header));
    }

    void Withdraw(uint64_t name)
    {
        RoleFluidHeader header;
        header.kind = KIND_WITHDRAW;
        header.name = name;
        header.hopLimit = HELLO_TTL;
        header.sendTime = Simulator::Now().GetSeconds();
        SendOnAll(MakePacket(header));
    }

    void HandleRead(Ptr<Socket> socket)
    {
        Address from;
        while (Ptr<Packet> packet = socket->RecvFrom(from))
        {
            if (!PacketSocketAddress::IsMatchingType(from))
            {
                continue;
            }
            const PacketSocketAddress address = PacketSocketAddress::ConvertFrom(from);
            const uint32_t ingress = address.GetSingleDevice();
            RoleFluidHeader header;
            if (packet->GetSize() < header.GetSerializedSize())
            {
                continue;
            }
            packet->RemoveHeader(header);
            if (ingress < deviceLatencyMs.size())
            {
                const double hopDelay = Simulator::Now().GetSeconds() - header.sendTime -
                                        deviceLatencyMs[ingress] / 1000.0;
                if (hopDelay > -0.001)
                {
                    const double delayMs = 1000.0 * std::max(0.0, hopDelay);
                    queueDelaySumMs += delayMs;
                    ++queueDelaySamples;
                    const double now = Simulator::Now().GetSeconds();
                    if (now >= MOVE_SECONDS && now < MOVE_SECONDS + 10.0)
                    {
                        shockQueueSumMs += delayMs;
                        ++shockQueueSamples;
                    }
                }
            }
            switch (header.kind)
            {
            case KIND_HELLO:
                OnHello(header, ingress);
                break;
            case KIND_WITHDRAW:
                OnWithdraw(header, ingress);
                break;
            case KIND_INTEREST:
                OnInterest(header, ingress);
                break;
            case KIND_DATA:
                OnData(header, ingress);
                break;
            default:
                break;
            }
        }
    }

    void OnHello(const RoleFluidHeader& header, uint32_t ingress)
    {
        latestHelloDevice[header.name] = ingress;
        const double latency = ingress < deviceLatencyMs.size() ? deviceLatencyMs[ingress] : 1.0;
        const uint16_t mtu = ingress < deviceMtu.size() ? deviceMtu[ingress] : 1500;
        const double cost = header.costAccum + latency;
        auto& entries = fib[header.name];
        bool improved = entries.empty() || cost < entries[0].latencyMs - 1e-6;
        if (!improved && cost <= entries[0].latencyMs + 1e-6)
        {
            // Equal-cost alternative ingress: useful for the balancer only.
            for (const auto& entry : entries)
            {
                if (entry.device == ingress)
                {
                    return;
                }
            }
            entries.push_back({ingress, cost, mtu});
            return;
        }
        if (!improved)
        {
            return; // a worse path; drop it
        }
        entries.clear();
        entries.push_back({ingress, cost, mtu});
        const double previous = bestCost[header.name];
        if (previous > 0.0 && cost >= previous - 1e-6)
        {
            return; // no global improvement worth re-flooding
        }
        bestCost[header.name] = cost;
        if (header.hopLimit <= 1)
        {
            return;
        }
        RoleFluidHeader forward = header;
        --forward.hopLimit;
        forward.costAccum = cost;
        forward.sendTime = Simulator::Now().GetSeconds();
        SendOnAll(MakePacket(forward), static_cast<int>(ingress));
    }

    void OnWithdraw(const RoleFluidHeader& header, uint32_t ingress)
    {
        if (dnsMode && isClient)
        {
            return; // a DNS-cached client ignores name-routing withdrawals
        }
        auto& entries = fib[header.name];
        entries.erase(std::remove_if(entries.begin(),
                                     entries.end(),
                                     [&](const FibEntry& entry) {
                                         return entry.device == ingress;
                                     }),
                      entries.end());
    }

    uint32_t ChooseEgress(uint64_t name, int ingress, double temperature)
    {
        const auto it = fib.find(name);
        if (it == fib.end() || it->second.empty())
        {
            return UINT32_MAX;
        }
        const auto& entries = it->second;
        std::vector<double> weights;
        for (const auto& entry : entries)
        {
            const double roleCost = role == ROLE_BALANCER ? 0.5 : 1.0;
            double phi = 0.35 * (entry.latencyMs / 500.0) + 0.10 * roleCost;
            if (static_cast<int>(entry.device) == ingress && entries.size() > 1)
            {
                phi += 0.5;
            }
            weights.push_back(std::exp(-phi / temperature));
        }
        if (balancerMode || role == ROLE_BALANCER)
        {
            double total = 0.0;
            for (double weight : weights)
            {
                total += weight;
            }
            double draw = m_uniform(m_rng) * total;
            for (size_t position = 0; position < weights.size(); ++position)
            {
                draw -= weights[position];
                if (draw <= 0.0)
                {
                    return entries[position].device;
                }
            }
            return entries.back().device;
        }
        size_t best = 0;
        for (size_t position = 1; position < weights.size(); ++position)
        {
            if (weights[position] > weights[best])
            {
                best = position;
            }
        }
        if (entries.size() == 1 && static_cast<int>(entries[best].device) == ingress)
        {
            return UINT32_MAX; // no forward progress possible
        }
        return entries[best].device;
    }

    uint64_t NameForSequence(uint32_t sequence) const
    {
        return static_cast<uint64_t>((sequence + index) % NAME_COUNT);
    }

    void ScheduleNextRequest()
    {
        const double now = Simulator::Now().GetSeconds();
        double rate = requestRate;
        if (shockwaveEnabled && now >= MOVE_SECONDS && now < MOVE_SECONDS + 10.0)
        {
            rate *= shockwaveMultiplier;
        }
        if (rate <= 0.0)
        {
            return;
        }
        Simulator::Schedule(Seconds(1.0 / rate), &FabricNode::SendInterest, this);
    }

    void SendInterest()
    {
        const uint32_t localSequence = m_nextSequence++;
        const uint64_t name = NameForSequence(localSequence);
        const uint32_t sequence = index * 1000000u + localSequence;
        const auto key = std::make_pair(name, sequence);
        interestFirstSent[key] = Simulator::Now().GetSeconds();
        ++interestsSent;
        SendInterestForKey(key);
        ScheduleNextRequest();
    }

    void SendInterestForKey(const std::pair<uint64_t, uint32_t>& key)
    {
        const uint64_t name = key.first;
        uint32_t egress = UINT32_MAX;
        if (dnsMode)
        {
            const auto frozen = frozenEgress.find(name);
            if (frozen == frozenEgress.end())
            {
                egress = ChooseEgress(name, -1, 0.35);
                if (egress != UINT32_MAX)
                {
                    frozenEgress[name] = egress;
                }
            }
            else
            {
                egress = frozen->second;
            }
            if (moveEnabled && name == 0 &&
                Simulator::Now().GetSeconds() >= MOVE_SECONDS + DNS_TTL_SECONDS)
            {
                const auto authoritative = latestHelloDevice.find(name);
                egress = authoritative != latestHelloDevice.end() ? authoritative->second : UINT32_MAX;
            }
        }
        else
        {
            egress = ChooseEgress(name, -1, 0.35);
        }
        if (egress == UINT32_MAX)
        {
            ++interestsUnresolved;
            return;
        }
        RoleFluidHeader header;
        header.kind = KIND_INTEREST;
        header.name = name;
        header.seq = key.second;
        header.mtu = 1500;
        header.hopLimit = 64;
        header.sendTime = Simulator::Now().GetSeconds();
        SendOn(egress, MakePacket(header));
        if (isClient && lossEnabled)
        {
            Simulator::Schedule(MilliSeconds(RTO_MS), &FabricNode::CheckTimeout, this, key);
        }
    }

    void CheckTimeout(const std::pair<uint64_t, uint32_t>& key)
    {
        const auto offsets = receivedOffsets.find(key);
        if (offsets == receivedOffsets.end() || offsets->second.empty())
        {
            return;
        }
        // Re-send only while there is a chance the object is incomplete; this
        // models a selective repeat request for the missing fragment.
        const uint32_t attempts = retransmissions[key]++;
        if (attempts < 2 && offsets->second.size() < FRAGMENTS_IN_OBJECT)
        {
            ++retransmissionsSent;
            SendInterestForKey(key);
        }
    }

    void OnInterest(const RoleFluidHeader& header, uint32_t ingress)
    {
        ++interestsForwarded;
        if (dnsMode && isServer && index == 0 && header.name == 0 &&
            Simulator::Now().GetSeconds() >= MOVE_SECONDS)
        {
            // In DNS mode the moved service leaves a dead address; the stale
            // server drops rather than forwarding on the name's behalf.
            ++interestsUnresolved;
            return;
        }
        const auto cached = cache.find(header.name);
        const auto cachedTotal = cacheTotal.find(header.name);
        const bool canServe = role == ROLE_SERVER && cached != cache.end() &&
                              cachedTotal != cacheTotal.end() &&
                              cached->second.size() >= cachedTotal->second;
        if (canServe)
        {
            ++localServes;
            ServeObject(header, ingress);
            return;
        }
        if (Serves(header.name, Simulator::Now().GetSeconds()))
        {
            ++objectsServed;
            ServeObject(header, ingress);
            return;
        }
        const auto key = std::make_pair(header.name, header.seq);
        pit[key] = {ingress, Simulator::Now().GetSeconds()};
        const uint32_t egress = ChooseEgress(header.name, static_cast<int>(ingress), 0.35);
        if (egress == UINT32_MAX)
        {
            ++interestsUnresolved;
            return;
        }
        RoleFluidHeader forward = header;
        if (forward.hopLimit == 0)
        {
            return;
        }
        --forward.hopLimit;
        if (egress < deviceMtu.size())
        {
            forward.mtu = std::min(forward.mtu, deviceMtu[egress]);
        }
        forward.sendTime = Simulator::Now().GetSeconds();
        SendOn(egress, MakePacket(forward));
    }

    void ServeObject(const RoleFluidHeader& interest, uint32_t ingress)
    {
        const uint16_t mtu = interest.mtu == 0 ? 1500 : interest.mtu;
        const uint32_t fragmentBytes = std::max(64u, static_cast<uint32_t>(mtu - 40));
        const uint32_t fragments =
            std::max(1u, (OBJECT_BYTES + fragmentBytes - 1) / fragmentBytes);
        for (uint32_t offset = 0; offset < OBJECT_BYTES; offset += fragmentBytes)
        {
            RoleFluidHeader header;
            header.kind = KIND_DATA;
            header.name = interest.name;
            header.seq = interest.seq;
            header.offset = static_cast<uint16_t>(offset / fragmentBytes);
            header.total = static_cast<uint16_t>(fragments);
            header.mtu = mtu;
            header.hopLimit = 20;
            header.sendTime = Simulator::Now().GetSeconds();
            Ptr<Packet> packet = MakePacket(header);
            const uint32_t chunk = std::min(fragmentBytes, OBJECT_BYTES - offset);
            packet->AddAtEnd(Create<Packet>(chunk));
            SendOn(ingress, packet);
            ++dataFragmentsSent;
        }
    }

    void OnData(const RoleFluidHeader& header, uint32_t ingress)
    {
        CacheFragment(header);
        if (isClient)
        {
            const auto key = std::make_pair(header.name, header.seq);
            auto& offsets = receivedOffsets[key];
            if (offsets.count(header.offset) > 0)
            {
                ++duplicates;
                return;
            }
            offsets.insert(header.offset);
            if (offsets.size() >= header.total)
            {
                const auto first = interestFirstSent.find(key);
                if (first != interestFirstSent.end())
                {
                    const double ttfb = 1000.0 * (Simulator::Now().GetSeconds() - first->second);
                    ttfbSumMs += ttfb;
                    ++ttfbSamples;
                }
                ++completedObjects;
                const auto sentAt = interestFirstSent.find(key);
                const bool sentAfterMove = sentAt != interestFirstSent.end() &&
                                           sentAt->second >= MOVE_SECONDS;
                if (moveEnabled && header.name == 0 && sentAfterMove)
                {
                    const auto found = firstSuccessAfterMove.find(header.name);
                    if (found == firstSuccessAfterMove.end())
                    {
                        firstSuccessAfterMove[header.name] =
                            Simulator::Now().GetSeconds() - MOVE_SECONDS;
                    }
                }
            }
            return;
        }
        const auto pitEntry = pit.find(std::make_pair(header.name, header.seq));
        if (pitEntry == pit.end())
        {
            return;
        }
        RoleFluidHeader forward = header;
        forward.sendTime = Simulator::Now().GetSeconds();
        SendOn(pitEntry->second.first, MakePacket(forward));
    }

    void CacheFragment(const RoleFluidHeader& header)
    {
        auto& object = cache[header.name];
        if (object.count(header.offset) == 0)
        {
            object[header.offset] = std::string();
            cacheTotal[header.name] = header.total;
            while (cache.size() > CACHE_OBJECTS)
            {
                const uint64_t victim = cache.begin()->first;
                cache.erase(cache.begin());
                cacheTotal.erase(victim);
            }
        }
    }

    void ControlTick()
    {
        const double now = Simulator::Now().GetSeconds();
        const double window = now - lastControl;
        lastControl = now;
        // Expire stale PIT entries so the table stays bounded.
        for (auto entry = pit.begin(); entry != pit.end();)
        {
            if (now - entry->second.second > PIT_LIFETIME_MS / 1000.0)
            {
                entry = pit.erase(entry);
            }
            else
            {
                ++entry;
            }
        }
        if (window > 0.0)
        {
            const double rate = static_cast<double>(interestsForwarded + localServes) / window;
            const double acceleration = (rate - lastRate) / window;
            const double alpha = 0.35;
            emaVelocity = (1.0 - alpha) * emaVelocity + alpha * rate;
            emaAcceleration = (1.0 - alpha) * emaAcceleration + alpha * acceleration;
            lastRate = rate;
            pressure = emaVelocity / 50.0 + 1.5 * emaAcceleration / 50.0;
            if (turbo)
            {
                MaybeSwitchRole();
            }
        }
        Simulator::Schedule(MilliSeconds(200), &FabricNode::ControlTick, this);
    }

    void MaybeSwitchRole()
    {
        if (pendingRole >= 0 && Simulator::Now().GetSeconds() >= pendingRoleAt)
        {
            role = pendingRole;
            pendingRole = -1;
            ++roleTransitions;
        }
        if (pendingRole >= 0)
        {
            return;
        }
        const double modulation = 1.0 + 2.0 * std::max(0.0, pressure) +
                                  6.0 * std::pow(std::max(0.0, pressure), 3.0);
        const bool hasCache = !cache.empty();
        int target = role;
        if (pressure * modulation > 3.0 && hasCache)
        {
            target = ROLE_SERVER;
        }
        else if (pressure > 0.6)
        {
            target = ROLE_BALANCER;
        }
        else if (pressure < 0.25 && role != ROLE_ROUTER && !isServer)
        {
            target = ROLE_ROUTER;
        }
        if (target != role)
        {
            pendingRole = target;
            pendingRoleAt = Simulator::Now().GetSeconds() + roleInertiaMs / 1000.0;
        }
    }

    Ptr<Socket> m_socket;
    std::mt19937 m_rng{12345};
    std::uniform_real_distribution<double> m_uniform{0.0, 1.0};
    uint32_t m_nextSequence{0};
};
} // namespace

int
main(int argc, char* argv[])
{
    std::string scenario = "A_static";
    uint32_t seed = 1;
    std::string out = "fabric.csv";

    CommandLine cmd(__FILE__);
    cmd.AddValue("scenario", "A_static|A_turbo|B_dns|B_name|C_single|C_fabric|stability", scenario);
    cmd.AddValue("seed", "replicate seed", seed);
    cmd.AddValue("out", "CSV output path", out);
    cmd.Parse(argc, argv);

    const bool turbo = scenario == "A_turbo" || scenario == "stability";
    const bool balancer = scenario == "C_fabric";
    const bool dns = scenario == "B_dns";
    const bool shockwave = scenario == "A_static" || scenario == "A_turbo";
    const bool move = scenario == "B_dns" || scenario == "B_name";
    const bool loss = scenario == "C_fabric";
    const double baseRate = scenario == "stability" ? 2.0 : 10.0;
    const double duration = scenario == "stability"
                                ? 10000.0
                                : (scenario == "B_dns" || scenario == "B_name" ? 420.0 : 120.0);

    NodeContainer nodes;
    nodes.Create(NODE_COUNT);

    std::vector<std::pair<uint32_t, uint32_t>> edges;
    for (uint32_t node = 0; node < NODE_COUNT; ++node)
    {
        edges.push_back({node, (node + 1) % NODE_COUNT});
    }
    for (uint32_t node = 0; node < 15; ++node)
    {
        edges.push_back({node, (node + 7) % NODE_COUNT});
    }

    PacketSocketHelper packetSocket;
    packetSocket.Install(nodes);

    PointToPointHelper fibre;
    fibre.SetDeviceAttribute("DataRate", StringValue("1Gbps"));
    fibre.SetChannelAttribute("Delay", StringValue("2ms"));
    PointToPointHelper satellite;
    satellite.SetDeviceAttribute("DataRate", StringValue("10Mbps"));
    satellite.SetChannelAttribute("Delay", StringValue("500ms"));
    CsmaHelper microwave;
    microwave.SetChannelAttribute("DataRate", StringValue("100Mbps"));
    microwave.SetChannelAttribute("Delay", StringValue("10ms"));

    std::vector<std::vector<double>> deviceLatency(NODE_COUNT);
    std::vector<std::vector<uint16_t>> deviceMtu(NODE_COUNT);

    uint32_t edgeIndex = 0;
    for (const auto& edge : edges)
    {
        int type = edgeIndex % 2;
        if (edgeIndex >= NODE_COUNT)
        {
            // Chords: satellite for the first few, fibre otherwise.
            type = (edgeIndex - NODE_COUNT) < 5 ? 2 : 0;
        }
        ++edgeIndex;
        NetDeviceContainer container;
        double latency = 2.0;
        uint16_t mtu = 1500;
        if (type == 0)
        {
            container = fibre.Install(nodes.Get(edge.first), nodes.Get(edge.second));
            latency = 2.0;
            mtu = 1500;
        }
        else if (type == 1)
        {
            NodeContainer pair;
            pair.Add(nodes.Get(edge.first));
            pair.Add(nodes.Get(edge.second));
            container = microwave.Install(pair);
            latency = 10.0;
            mtu = 1500;
        }
        else
        {
            container = satellite.Install(nodes.Get(edge.first), nodes.Get(edge.second));
            latency = 500.0;
            mtu = 500;
        }
        if (loss && type == 2)
        {
            Ptr<RateErrorModel> error = CreateObject<RateErrorModel>();
            error->SetAttribute("ErrorRate", DoubleValue(0.005));
            error->SetAttribute("ErrorUnit", EnumValue(RateErrorModel::ERROR_UNIT_PACKET));
            for (uint32_t dev = 0; dev < container.GetN(); ++dev)
            {
                container.Get(dev)->SetAttribute("ReceiveErrorModel", PointerValue(error));
            }
        }
        deviceLatency[edge.first].push_back(latency);
        deviceLatency[edge.second].push_back(latency);
        deviceMtu[edge.first].push_back(mtu);
        deviceMtu[edge.second].push_back(mtu);
    }

    std::vector<Ptr<FabricNode>> apps;
    for (uint32_t node = 0; node < NODE_COUNT; ++node)
    {
        Ptr<FabricNode> app = CreateObject<FabricNode>();
        const bool server = node % 5 == 0;
        const bool client = node % 10 == 2;
        app->ConfigureNode(node, server, client, turbo, balancer, dns, baseRate,
                           shockwave, move, loss);
        app->deviceLatencyMs = deviceLatency[node];
        app->deviceMtu = deviceMtu[node];
        nodes.Get(node)->AddApplication(app);
        app->SetStartTime(Seconds(0.0));
        app->SetStopTime(Seconds(duration));
        apps.push_back(app);
    }

    Simulator::Stop(Seconds(duration));
    Simulator::Run();


    uint64_t transitions = 0;
    uint64_t retransmissions = 0;
    uint64_t unresolved = 0;
    uint64_t ttfbs = 0;
    double ttfbSum = 0.0;
    double queueSum = 0.0;
    uint64_t queueSamples = 0;
    double shockQueueSum = 0.0;
    uint64_t shockQueueSamples = 0;
    double firstSuccess = -1.0;
    for (const auto& app : apps)
    {
        transitions += app->roleTransitions;
        retransmissions += app->retransmissionsSent;
        unresolved += app->interestsUnresolved;
        ttfbs += app->ttfbSamples;
        ttfbSum += app->ttfbSumMs;
        queueSum += app->queueDelaySumMs;
        queueSamples += app->queueDelaySamples;
        shockQueueSum += app->shockQueueSumMs;
        shockQueueSamples += app->shockQueueSamples;
        if (move && firstSuccess < 0.0 && !app->firstSuccessAfterMove.empty())
        {
            firstSuccess = app->firstSuccessAfterMove.begin()->second;
        }
    }

    const bool fresh = std::ifstream(out).peek() == std::ifstream::traits_type::eof();
    std::ofstream csv(out, std::ios::app);
    if (!csv.is_open())
    {
        NS_FATAL_ERROR("Cannot open " << out);
    }
    if (fresh)
    {
        csv << "scenario,seed,duration_s,role_transitions,mean_queue_delay_ms,"
               "shockwave_queue_delay_ms,mean_ttfb_ms,packet_drop_rate_percent,"
               "retransmissions,first_success_after_move_s\n";
    }
    uint64_t sentTotal = 0;
    for (const auto& app : apps)
    {
        sentTotal += app->interestsSent;
    }
    const double dropRate = 100.0 * static_cast<double>(unresolved + retransmissions) /
                            std::max<uint64_t>(1, sentTotal);
    csv << scenario << "," << seed << "," << duration << "," << transitions << ","
        << (queueSamples ? queueSum / queueSamples : 0.0) << ","
        << (shockQueueSamples ? shockQueueSum / shockQueueSamples : 0.0) << ","
        << (ttfbs ? ttfbSum / ttfbs : 0.0) << "," << dropRate << "," << retransmissions << ","
        << firstSuccess << "\n";
    csv.close();

    std::printf("scenario=%s seed=%u transitions=%llu queue_mean=%.2fms shock_queue=%.2fms "
                "ttfb=%.2fms drop=%.2f%% retrans=%llu first_success_after_move=%.2fs\n",
                scenario.c_str(), seed,
                static_cast<unsigned long long>(transitions),
                queueSamples ? queueSum / queueSamples : 0.0,
                shockQueueSamples ? shockQueueSum / shockQueueSamples : 0.0,
                ttfbs ? ttfbSum / ttfbs : 0.0,
                dropRate,
                static_cast<unsigned long long>(retransmissions),
                firstSuccess);

    Simulator::Destroy();
    return 0;
}
