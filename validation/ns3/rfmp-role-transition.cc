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
 * RFMP v0.1 reference implementation: scenario RT1 (role transition).
 *
 * Specifies the protocol in docs/rfmp-protocol.md and mirrors the Python
 * discrete-event reference in simulation/rfmp.py. Both implementations use the
 * same constants, the same deterministic send-time jitter (a hash of seed and
 * packet index, so seeds pair exactly across implementations), the same smooth
 * weighted round-robin path selection, the same reordering buffer and the same
 * role-transition overlap.
 *
 * The ns-3 point-to-point rate on the MTU-1200 path is scaled to 6.4 Mbit/s to
 * emulate the 1.25x per-packet overhead the Python model applies explicitly;
 * that keeps the effective serialization equal on both sides.
 *
 * Usage:
 *   ns3.49-rfmp-role-transition-default --seed=1 --out=rt1.csv --append=0
 */

#include "ns3/applications-module.h"
#include "ns3/core-module.h"
#include "ns3/internet-module.h"
#include "ns3/network-module.h"
#include "ns3/point-to-point-module.h"
#include "ns3/traffic-control-module.h"

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <deque>
#include <fstream>
#include <map>
#include <numeric>
#include <set>
#include <string>
#include <vector>

using namespace ns3;

namespace
{
// ---- Shared constants (mirror simulation/rfmp.py) --------------------------
constexpr uint32_t PAYLOAD_BYTES = 1200;
constexpr uint32_t WIRE_BYTES = 1228;
constexpr double INTERVAL = 0.0008;
constexpr double DURATION = 20.0;
constexpr uint64_t PACKET_COUNT = 25000;
constexpr double JITTER_SECONDS = 0.05e-3;
constexpr double CONTROL_INTERVAL = 0.1;
constexpr double UTILIZATION_WINDOW = 0.5;
constexpr double HANDOFF_HEADSTART = 0.05;
constexpr double HANDOFF_TAIL = 0.05;
constexpr double REORDER_DEADLINE = 0.2;
constexpr double SERVE_START = 6.0;
constexpr double SERVE_END = 12.0;
constexpr uint32_t QUEUE_LIMIT = 100;
constexpr double PATH0_RATE_MBPS = 20.0;
constexpr double PATH1_RATE_MBPS = 6.4; // 8 / 1.25 effective
constexpr double EDGE_RATE_MBPS = 30.0;
constexpr double PATH0_DELAY_MS = 4.0;
constexpr double PATH1_DELAY_MS = 20.0;
constexpr double EDGE_DELAY_MS = 2.0;
constexpr uint32_t PATH0_NOMINAL_MBPS = 20;
constexpr uint32_t PATH1_NOMINAL_MBPS = 8;

struct Header
{
    uint64_t seq;
    double sendTime;
    uint8_t source;
    uint8_t path;
    uint16_t flags;
    uint32_t contentId;
};

double
Jitter(uint32_t seed, uint64_t index)
{
    uint32_t x = seed * 0x9E3779B1u + static_cast<uint32_t>(index) + 0x85EBCA6Bu;
    x ^= x >> 13;
    x *= 0x85EBCA6Bu;
    x ^= x >> 16;
    const double unit = static_cast<double>(x) / 4294967295.0;
    return (unit * 2.0 - 1.0) * JITTER_SECONDS;
}

double
PacketTime(uint32_t seed, uint64_t index)
{
    return std::max(0.0, static_cast<double>(index) * INTERVAL + Jitter(seed, index));
}

bool
OriginActive(double timestamp)
{
    return timestamp < SERVE_START + HANDOFF_TAIL || timestamp >= SERVE_END - HANDOFF_HEADSTART;
}

bool
ServingActive(double timestamp)
{
    return timestamp >= SERVE_START - HANDOFF_HEADSTART && timestamp < SERVE_END + HANDOFF_TAIL;
}

// ---- Sender with smooth weighted round-robin -------------------------------
class RfmpSender : public Application
{
  public:
    static TypeId GetTypeId();

    void Configure(uint32_t seed, Ipv4Address path0, Ipv4Address path1, bool dualPath)
    {
        m_seed = seed;
        m_remotes[0] = path0;
        m_remotes[1] = path1;
        m_dualPath = dualPath;
        m_log.resize(dualPath ? 2 : 1);
        m_deficit.assign(m_dualPath ? 2 : 1, 0.0);
        m_weights.assign(m_dualPath ? 2 : 1, 0.0);
    }

    uint64_t emitted{0};

  private:
    void StartApplication() override
    {
        const uint32_t socketCount = m_dualPath ? 2 : 1;
        for (uint32_t index = 0; index < socketCount; ++index)
        {
            m_sockets[index] = Socket::CreateSocket(GetNode(), UdpSocketFactory::GetTypeId());
            m_sockets[index]->Connect(InetSocketAddress(m_remotes[index], 9000));
        }
        for (uint64_t sequence = 0; sequence < PACKET_COUNT; ++sequence)
        {
            const double timestamp = PacketTime(m_seed, sequence);
            const bool active = m_dualPath ? OriginActive(timestamp) : ServingActive(timestamp);
            if (active)
            {
                Simulator::Schedule(Seconds(timestamp), &RfmpSender::SendOne, this, sequence, timestamp);
            }
        }
    }

    void StopApplication() override
    {
        for (auto& socket : m_sockets)
        {
            if (socket)
            {
                socket->Close();
            }
        }
    }

    void RecomputeWeights(double now)
    {
        double total = 0.0;
        for (uint32_t index = 0; index < m_weights.size(); ++index)
        {
            auto& log = m_log[index];
            while (!log.empty() && log.front().first < now - UTILIZATION_WINDOW)
            {
                log.pop_front();
            }
            double bytes = 0.0;
            for (const auto& entry : log)
            {
                bytes += entry.second;
            }
            const double capacity =
                (index == 0 ? PATH0_NOMINAL_MBPS : PATH1_NOMINAL_MBPS) * 1e6 / 8.0;
            const double utilization = std::min(1.0, bytes / (capacity * UTILIZATION_WINDOW));
            const double latency = index == 0 ? PATH0_DELAY_MS : PATH1_DELAY_MS;
            m_weights[index] = std::max(1e-9, capacity * 8.0 / 1e6 / (latency + 1.0) *
                                                 (1.0 - utilization));
            total += m_weights[index];
        }
        m_weightTotal = total;
    }

    uint32_t ChoosePath(double now)
    {
        if (now >= m_nextControl || m_weightTotal <= 0.0)
        {
            RecomputeWeights(now);
            m_nextControl = (std::floor(now / CONTROL_INTERVAL) + 1.0) * CONTROL_INTERVAL;
        }
        uint32_t best = 0;
        double bestDeficit = -1e18;
        for (uint32_t index = 0; index < m_deficit.size(); ++index)
        {
            m_deficit[index] += m_weights[index] / m_weightTotal;
            if (m_deficit[index] > bestDeficit)
            {
                bestDeficit = m_deficit[index];
                best = index;
            }
        }
        m_deficit[best] -= 1.0;
        return best;
    }

    void SendOne(uint64_t sequence, double timestamp)
    {
        uint32_t path = 0;
        if (m_dualPath)
        {
            path = ChoosePath(timestamp);
            m_log[path].push_back({timestamp, WIRE_BYTES});
        }
        Header header{sequence, timestamp, m_dualPath ? 0u : 1u, static_cast<uint8_t>(path), 0u, 1u};
        std::vector<uint8_t> buffer(PAYLOAD_BYTES, 0);
        std::memcpy(buffer.data(), &header, sizeof(header));
        m_sockets[path]->Send(buffer.data(), PAYLOAD_BYTES, 0);
        ++emitted;
    }

    Ptr<Socket> m_sockets[2];
    Ipv4Address m_remotes[2];
    uint32_t m_seed{1};
    bool m_dualPath{true};
    std::vector<std::deque<std::pair<double, double>>> m_log;
    std::vector<double> m_deficit;
    std::vector<double> m_weights;
    double m_weightTotal{0.0};
    double m_nextControl{0.0};
};

TypeId
RfmpSender::GetTypeId()
{
    static TypeId tid = TypeId("RfmpSender")
                            .SetParent<Application>()
                            .SetGroupName("Applications")
                            .AddConstructor<RfmpSender>();
    return tid;
}

// ---- Forwarder -------------------------------------------------------------
class RfmpForwarder : public Application
{
  public:
    static TypeId GetTypeId();

    void Configure(Ipv4Address downstream) { m_downstream = downstream; }

  private:
    void StartApplication() override
    {
        m_in = Socket::CreateSocket(GetNode(), UdpSocketFactory::GetTypeId());
        m_in->Bind(InetSocketAddress(Ipv4Address::GetAny(), 9000));
        m_in->SetRecvCallback(MakeCallback(&RfmpForwarder::HandleRead, this));
        m_out = Socket::CreateSocket(GetNode(), UdpSocketFactory::GetTypeId());
        m_out->Connect(InetSocketAddress(m_downstream, 9000));
    }

    void StopApplication() override
    {
        for (auto& socket : {m_in, m_out})
        {
            if (socket)
            {
                socket->Close();
            }
        }
    }

    void HandleRead(Ptr<Socket> socket)
    {
        while (Ptr<Packet> packet = socket->Recv())
        {
            const uint32_t size = packet->GetSize();
            std::vector<uint8_t> buffer(size);
            packet->CopyData(buffer.data(), size);
            m_out->Send(buffer.data(), size, 0);
        }
    }

    Ipv4Address m_downstream;
    Ptr<Socket> m_in;
    Ptr<Socket> m_out;
};

TypeId
RfmpForwarder::GetTypeId()
{
    static TypeId tid = TypeId("RfmpForwarder")
                            .SetParent<Application>()
                            .SetGroupName("Applications")
                            .AddConstructor<RfmpForwarder>();
    return tid;
}

// ---- Receiver: reordering buffer, duplicate suppression, metrics -----------
class RfmpReceiver : public Application
{
  public:
    static TypeId GetTypeId();

    uint64_t arrivals{0};
    uint64_t duplicates{0};
    uint64_t handoffDuplicates{0};
    uint64_t released{0};
    uint64_t late{0};
    std::vector<double> stalls;
    std::vector<double> delays;
    std::vector<std::pair<double, uint64_t>> releases;

  private:
    void StartApplication() override
    {
        m_socket = Socket::CreateSocket(GetNode(), UdpSocketFactory::GetTypeId());
        m_socket->Bind(InetSocketAddress(Ipv4Address::GetAny(), 9000));
        m_socket->SetRecvCallback(MakeCallback(&RfmpReceiver::HandleRead, this));
    }

    void StopApplication() override
    {
        if (m_socket)
        {
            m_socket->Close();
        }
    }

    static bool InHandoffWindow(double timestamp)
    {
        return (timestamp >= SERVE_START - HANDOFF_HEADSTART &&
                timestamp < SERVE_START + HANDOFF_TAIL) ||
               (timestamp >= SERVE_END - HANDOFF_HEADSTART && timestamp < SERVE_END + HANDOFF_TAIL);
    }

    void ReleaseReady(double now)
    {
        while (true)
        {
            auto entry = m_buffer.find(m_nextExpected);
            if (entry == m_buffer.end())
            {
                break;
            }
            const double stall = std::max(0.0, now - entry->second.first);
            stalls.push_back(stall);
            delays.push_back(std::max(0.0, now - entry->second.second));
            releases.push_back({now, m_nextExpected});
            m_buffer.erase(entry);
            ++m_nextExpected;
            ++released;
        }
    }

    void HandleRead(Ptr<Socket> socket)
    {
        while (Ptr<Packet> packet = socket->Recv())
        {
            if (packet->GetSize() < sizeof(Header))
            {
                continue;
            }
            uint8_t buffer[PAYLOAD_BYTES];
            const uint32_t size = std::min<uint32_t>(packet->GetSize(), PAYLOAD_BYTES);
            packet->CopyData(buffer, size);
            Header header;
            std::memcpy(&header, buffer, sizeof(header));
            const double now = Simulator::Now().GetSeconds();
            ++arrivals;

            bool duplicate = false;
            if (header.seq < m_nextExpected)
            {
                duplicate = true;
            }
            else if (m_buffer.find(header.seq) != m_buffer.end())
            {
                duplicate = true;
            }
            if (duplicate)
            {
                ++duplicates;
                if (InHandoffWindow(now) && m_handoffSeen.insert(header.seq).second)
                {
                    ++handoffDuplicates;
                }
                continue;
            }

            m_buffer[header.seq] = {now, header.sendTime};
            ReleaseReady(now);

            if (!m_buffer.empty())
            {
                const auto lowest = m_buffer.begin();
                if (lowest->first > m_nextExpected &&
                    now - lowest->second.first > REORDER_DEADLINE)
                {
                    late += lowest->first - m_nextExpected;
                    m_nextExpected = lowest->first;
                    ReleaseReady(now);
                }
            }
        }
    }

    std::map<uint64_t, std::pair<double, double>> m_buffer;
    std::set<uint64_t> m_handoffSeen;
    uint64_t m_nextExpected{0};
    Ptr<Socket> m_socket;
};

TypeId
RfmpReceiver::GetTypeId()
{
    static TypeId tid = TypeId("RfmpReceiver")
                            .SetParent<Application>()
                            .SetGroupName("Applications")
                            .AddConstructor<RfmpReceiver>();
    return tid;
}

double
Percentile(std::vector<double> values, double percentile)
{
    if (values.empty())
    {
        return 0.0;
    }
    std::sort(values.begin(), values.end());
    const double rank = percentile / 100.0 * static_cast<double>(values.size() - 1);
    const size_t lower = static_cast<size_t>(rank);
    const size_t upper = std::min(lower + 1, values.size() - 1);
    const double fraction = rank - static_cast<double>(lower);
    return values[lower] + (values[upper] - values[lower]) * fraction;
}

double
TransitionGap(const std::vector<std::pair<double, uint64_t>>& releases, double boundary)
{
    double before = -1.0;
    double after = -1.0;
    for (const auto& entry : releases)
    {
        if (entry.first < boundary)
        {
            before = std::max(before, entry.first);
        }
        else if (after < 0.0)
        {
            after = entry.first;
        }
    }
    if (before < 0.0 || after < 0.0)
    {
        return 0.0;
    }
    return 1000.0 * (after - before);
}

} // namespace

int
main(int argc, char* argv[])
{
    uint32_t seed = 1;
    std::string outputPath = "rt1.csv";
    bool append = false;

    CommandLine cmd(__FILE__);
    cmd.AddValue("seed", "replicate seed (selects the jitter sequence)", seed);
    cmd.AddValue("out", "CSV output path", outputPath);
    cmd.AddValue("append", "append to an existing CSV", append);
    cmd.Parse(argc, argv);

    NodeContainer nodes;
    nodes.Create(3); // 0 = O, 1 = X, 2 = D

    PointToPointHelper pointToPoint;
    pointToPoint.SetQueue("ns3::DropTailQueue", "MaxSize", QueueSizeValue(QueueSize("100p")));
    std::vector<NetDeviceContainer> links;
    std::vector<Ipv4InterfaceContainer> interfaces;

    InternetStackHelper internet;

    auto configure = [&](const char* rate, const char* delay) {
        pointToPoint.SetDeviceAttribute("DataRate", StringValue(rate));
        pointToPoint.SetChannelAttribute("Delay", StringValue(delay));
    };

    configure("20Mbps", "4ms");
    links.push_back(pointToPoint.Install(nodes.Get(0), nodes.Get(1)));
    configure("6.4Mbps", "20ms");
    links.push_back(pointToPoint.Install(nodes.Get(0), nodes.Get(1)));
    configure("30Mbps", "2ms");
    links.push_back(pointToPoint.Install(nodes.Get(1), nodes.Get(2)));

    internet.Install(nodes);

    const char* subnets[3] = {"10.0.0.0", "10.0.1.0", "10.0.2.0"};
    for (int index = 0; index < 3; ++index)
    {
        Ipv4AddressHelper address;
        address.SetBase(subnets[index], "255.255.255.0");
        interfaces.push_back(address.Assign(links[index]));
    }
    Ipv4GlobalRoutingHelper::PopulateRoutingTables();

    // Remove the default FqCoDel disc so the device drop-tail queue (100 packets)
    // is the only buffer, matching the Python model's DropTailQueue.
    for (uint32_t nodeIndex : {0u, 1u})
    {
        Ptr<TrafficControlLayer> tc = nodes.Get(nodeIndex)->GetObject<TrafficControlLayer>();
        for (uint32_t device = 0; device < nodes.Get(nodeIndex)->GetNDevices(); ++device)
        {
            Ptr<NetDevice> netDevice = nodes.Get(nodeIndex)->GetDevice(device);
            if (tc->GetRootQueueDiscOnDevice(netDevice))
            {
                tc->DeleteRootQueueDiscOnDevice(netDevice);
            }
        }
    }

    const Ipv4Address path0Address = interfaces[0].GetAddress(1);
    const Ipv4Address path1Address = interfaces[1].GetAddress(1);
    const Ipv4Address edgeAddress = interfaces[2].GetAddress(1);

    Ptr<RfmpSender> origin = CreateObject<RfmpSender>();
    origin->Configure(seed, path0Address, path1Address, true);
    nodes.Get(0)->AddApplication(origin);
    origin->SetStartTime(Seconds(0.0));
    origin->SetStopTime(Seconds(DURATION + 1.0));

    Ptr<RfmpForwarder> forwarder = CreateObject<RfmpForwarder>();
    forwarder->Configure(edgeAddress);
    nodes.Get(1)->AddApplication(forwarder);
    forwarder->SetStartTime(Seconds(0.0));
    forwarder->SetStopTime(Seconds(DURATION + 1.0));

    Ptr<RfmpSender> serving = CreateObject<RfmpSender>();
    serving->Configure(seed, edgeAddress, edgeAddress, false);
    nodes.Get(1)->AddApplication(serving);
    serving->SetStartTime(Seconds(0.0));
    serving->SetStopTime(Seconds(DURATION + 1.0));

    Ptr<RfmpReceiver> receiver = CreateObject<RfmpReceiver>();
    nodes.Get(2)->AddApplication(receiver);
    receiver->SetStartTime(Seconds(0.0));
    receiver->SetStopTime(Seconds(DURATION + 1.0));

    Simulator::Stop(Seconds(DURATION + 1.0));
    Simulator::Run();

    const double delivery = 100.0 * static_cast<double>(receiver->released) / PACKET_COUNT;
    const double duplicateRate =
        100.0 * static_cast<double>(receiver->duplicates) /
        std::max<uint64_t>(1, receiver->arrivals);
    const double handoffRate =
        100.0 * static_cast<double>(receiver->handoffDuplicates) /
        std::max<uint64_t>(1, receiver->arrivals);
    const double meanDelay = receiver->delays.empty()
                                 ? 0.0
                                 : 1000.0 * std::accumulate(receiver->delays.begin(),
                                                            receiver->delays.end(),
                                                            0.0) /
                                       static_cast<double>(receiver->delays.size());
    const double latePercent =
        100.0 * static_cast<double>(receiver->late) / static_cast<double>(PACKET_COUNT);

    std::ofstream out;
    out.open(outputPath, append ? std::ios::app : std::ios::trunc);
    if (!out.is_open())
    {
        NS_FATAL_ERROR("Cannot open " << outputPath);
    }
    if (!append)
    {
        out << "scenario,policy,seed,in_order_delivery_percent,duplicate_percent,"
               "handoff_duplicate_percent,transition_gap_6s_ms,transition_gap_12s_ms,"
               "reorder_stall_p95_ms,reorder_stall_max_ms,mean_delivery_delay_ms,late_drop_percent\n";
    }
    out << "rt1_role_transition,rfmp_ns3," << seed << "," << delivery << "," << duplicateRate << ","
        << handoffRate << "," << TransitionGap(receiver->releases, SERVE_START) << ","
        << TransitionGap(receiver->releases, SERVE_END) << ","
        << Percentile(receiver->stalls, 95.0) * 1000.0 << ","
        << (receiver->stalls.empty() ? 0.0 : *std::max_element(receiver->stalls.begin(),
                                                               receiver->stalls.end()) *
                                                  1000.0)
        << "," << meanDelay << "," << latePercent << "\n";
    out.close();

    std::printf("rt1 seed=%u released=%llu arrivals=%llu duplicates=%llu\n",
                seed,
                static_cast<unsigned long long>(receiver->released),
                static_cast<unsigned long long>(receiver->arrivals),
                static_cast<unsigned long long>(receiver->duplicates));

    Simulator::Destroy();
    return 0;
}
