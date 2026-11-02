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
 * Cross-validation scenario S1: two-path smooth weighted round-robin
 * scheduling of a constant-bit-rate packet stream with a handover window.
 *
 * This program is the ns-3 half of the experiment in
 * docs/external-validation.md. The scenario constants are mirrored verbatim
 * from validation/scenario_s1.py; change both or neither.
 *
 * ns-3 version used for the published comparison: ns-3.49
 *   ./ns3 configure --enable-modules=core,network,internet,point-to-point,csma,applications,traffic-control \
 *                   --disable-examples --disable-tests --disable-python
 *
 * Usage:
 *   s1-multipath-handover --scenario=s0_nominal|s1_handover --seed=1 \
 *                         --out=results.csv [--append=1]
 */

#include "ns3/applications-module.h"
#include "ns3/core-module.h"
#include "ns3/error-model.h"
#include "ns3/internet-module.h"
#include "ns3/network-module.h"
#include "ns3/point-to-point-module.h"
#include "ns3/traffic-control-module.h"

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <fstream>
#include <sstream>
#include <string>
#include <vector>

using namespace ns3;

namespace
{
// ---- Shared scenario constants (mirror validation/scenario_s1.py) ----------
constexpr double DURATION_SECONDS = 20.0;
constexpr uint32_t PACKET_BYTES = 1200;
constexpr double OFFERED_RATE_MBPS = 12.0;
constexpr double HANDOVER_START_SECONDS = 8.0;
constexpr double HANDOVER_END_SECONDS = 12.0;
constexpr double SCORE_LATENCY_OFFSET_MS = 1.0;
constexpr uint32_t QUEUE_LIMIT_PACKETS = 100;
constexpr uint32_t PATH_COUNT = 2;

struct PathSpec
{
    const char* name;
    double capacityMbps;
    double oneWayDelayMs;
    double lossProbability;
};

const PathSpec PATHS[PATH_COUNT] = {
    {"fiber_primary", 20.0, 5.0, 0.001},
    {"cellular_secondary", 8.0, 25.0, 0.005},
};

struct Payload
{
    uint64_t seq;
    double sendTimeSeconds;
};

// ---- Sender ---------------------------------------------------------------
class S1Sender : public Application
{
  public:
    static TypeId GetTypeId();

    void Configure(bool handover, const Ipv4Address& primary, const Ipv4Address& secondary)
    {
        m_handover = handover;
        m_remotes[0] = primary;
        m_remotes[1] = secondary;
    }

    //! Metrics accumulated for the CSV row.
    double activePathSamples{0.0};
    uint64_t assignedPrimary{0};
    uint64_t sentPackets{0};

  private:
    void StartApplication() override;
    void StopApplication() override;
    void SendOne(uint64_t seq);

    bool PrimaryAvailable(double t) const
    {
        return !(m_handover && t >= HANDOVER_START_SECONDS && t < HANDOVER_END_SECONDS);
    }

    Ptr<Socket> m_sockets[PATH_COUNT];
    Ipv4Address m_remotes[PATH_COUNT];
    double m_deficits[PATH_COUNT]{0.0, 0.0};
    bool m_handover{false};
    uint64_t m_packetCount{0};
    double m_intervalSeconds{0.0};
};

TypeId
S1Sender::GetTypeId()
{
    static TypeId tid = TypeId("S1Sender")
                            .SetParent<Application>()
                            .SetGroupName("Applications")
                            .AddConstructor<S1Sender>();
    return tid;
}

void
S1Sender::StartApplication()
{
    m_intervalSeconds = PACKET_BYTES * 8.0 / (OFFERED_RATE_MBPS * 1e6);
    m_packetCount = static_cast<uint64_t>(std::llround(DURATION_SECONDS / m_intervalSeconds));
    const uint16_t port = 9000;
    for (uint32_t index = 0; index < PATH_COUNT; ++index)
    {
        m_sockets[index] = Socket::CreateSocket(GetNode(), UdpSocketFactory::GetTypeId());
        m_sockets[index]->Connect(InetSocketAddress(m_remotes[index], port));
    }
    for (uint64_t seq = 0; seq < m_packetCount; ++seq)
    {
        Simulator::Schedule(Seconds(seq * m_intervalSeconds), &S1Sender::SendOne, this, seq);
    }
}

void
S1Sender::StopApplication()
{
    for (auto& socket : m_sockets)
    {
        if (socket)
        {
            socket->Close();
        }
    }
}

void
S1Sender::SendOne(uint64_t seq)
{
    const double now = Simulator::Now().GetSeconds();
    double scores[PATH_COUNT];
    double weightTotal = 0.0;
    activePathSamples += PrimaryAvailable(now) ? PATH_COUNT : 1;
    for (uint32_t index = 0; index < PATH_COUNT; ++index)
    {
        const bool available = (index == 0) ? PrimaryAvailable(now) : true;
        scores[index] = available
                           ? PATHS[index].capacityMbps /
                                 (PATHS[index].oneWayDelayMs + SCORE_LATENCY_OFFSET_MS)
                           : 0.0;
        weightTotal += scores[index];
    }

    // Smooth weighted round-robin: add the normalised weight, pick the largest debt.
    uint32_t selected = 0;
    double best = -1e9;
    for (uint32_t index = 0; index < PATH_COUNT; ++index)
    {
        m_deficits[index] += scores[index] / weightTotal;
        if (m_deficits[index] > best)
        {
            best = m_deficits[index];
            selected = index;
        }
    }
    m_deficits[selected] -= 1.0;
    if (selected == 0)
    {
        ++assignedPrimary;
    }

    Payload payload{seq, now};
    std::vector<uint8_t> buffer(PACKET_BYTES, 0);
    std::memcpy(buffer.data(), &payload, sizeof(payload));
    m_sockets[selected]->Send(buffer.data(), PACKET_BYTES, 0);
    ++sentPackets;
}

// ---- Receiver -------------------------------------------------------------
class S1Receiver : public Application
{
  public:
    static TypeId GetTypeId();

    std::vector<double> delaysMs;
    uint64_t receivedPackets{0};

  private:
    void StartApplication() override;
    void StopApplication() override;
    void HandleRead(Ptr<Socket> socket);

    Ptr<Socket> m_socket;
};

TypeId
S1Receiver::GetTypeId()
{
    static TypeId tid = TypeId("S1Receiver")
                            .SetParent<Application>()
                            .SetGroupName("Applications")
                            .AddConstructor<S1Receiver>();
    return tid;
}

void
S1Receiver::StartApplication()
{
    m_socket = Socket::CreateSocket(GetNode(), UdpSocketFactory::GetTypeId());
    m_socket->Bind(InetSocketAddress(Ipv4Address::GetAny(), 9000));
    m_socket->SetRecvCallback(MakeCallback(&S1Receiver::HandleRead, this));
}

void
S1Receiver::StopApplication()
{
    if (m_socket)
    {
        m_socket->Close();
    }
}

void
S1Receiver::HandleRead(Ptr<Socket> socket)
{
    while (Ptr<Packet> packet = socket->Recv())
    {
        uint8_t buffer[PACKET_BYTES];
        const uint32_t size = packet->GetSize();
        if (size < sizeof(Payload))
        {
            continue;
        }
        packet->CopyData(buffer, size);
        Payload payload;
        std::memcpy(&payload, buffer, sizeof(payload));
        delaysMs.push_back((Simulator::Now().GetSeconds() - payload.sendTimeSeconds) * 1000.0);
        ++receivedPackets;
    }
}

double
Percentile95(std::vector<double> values)
{
    if (values.empty())
    {
        return 0.0;
    }
    std::sort(values.begin(), values.end());
    const double rank = 0.95 * static_cast<double>(values.size() - 1);
    const size_t lower = static_cast<size_t>(rank);
    const size_t upper = std::min(lower + 1, values.size() - 1);
    const double fraction = rank - static_cast<double>(lower);
    return values[lower] + (values[upper] - values[lower]) * fraction;
}

} // namespace

int
main(int argc, char* argv[])
{
    std::string scenario = "s1_handover";
    uint32_t seed = 1;
    std::string outputPath = "ns3_s1.csv";
    bool append = false;

    CommandLine cmd(__FILE__);
    cmd.AddValue("scenario", "s0_nominal or s1_handover", scenario);
    cmd.AddValue("seed", "ns-3 RNG seed", seed);
    cmd.AddValue("out", "CSV output path", outputPath);
    cmd.AddValue("append", "Append to an existing CSV (skip the header)", append);
    cmd.Parse(argc, argv);

    if (scenario != "s0_nominal" && scenario != "s1_handover")
    {
        NS_FATAL_ERROR("Unknown scenario: " << scenario);
    }
    const bool handover = scenario == "s1_handover";

    RngSeedManager::SetSeed(seed);
    RngSeedManager::SetRun(seed);

    NodeContainer nodes;
    nodes.Create(2);

    PointToPointHelper pointToPoint;
    // One slot only: the traffic-control FIFO disc below is the S1 queue.
    pointToPoint.SetQueue("ns3::DropTailQueue", "MaxSize", QueueSizeValue(QueueSize("1p")));
    std::vector<NetDeviceContainer> pathDevices;

    for (uint32_t index = 0; index < PATH_COUNT; ++index)
    {
        std::ostringstream rate;
        rate << PATHS[index].capacityMbps << "Mbps";
        std::ostringstream delay;
        delay << PATHS[index].oneWayDelayMs << "ms";
        pointToPoint.SetDeviceAttribute("DataRate", StringValue(rate.str()));
        pointToPoint.SetChannelAttribute("Delay", StringValue(delay.str()));
        pathDevices.push_back(pointToPoint.Install(nodes.Get(0), nodes.Get(1)));
    }

    InternetStackHelper internet;
    internet.Install(nodes);

    // ns-3.49's InternetStackHelper installs a default FqCoDel queue disc with a
    // 10 240-packet limit on every device, and the point-to-point device keeps
    // its own drop-tail TxQueue. The S1 specification calls for exactly one
    // 100-packet FIFO drop-tail buffer, so the default disc is replaced by a
    // 100-packet FIFO disc and the device queue is reduced to a single slot
    // (the in-flight packet). Leaving ns-3's defaults in place instead yields a
    // 10 240-packet CoDel buffer and multi-second latency tails.
    NetDeviceContainer clientDevices;
    for (auto& devices : pathDevices)
    {
        clientDevices.Add(devices.Get(0));
    }
    Ptr<TrafficControlLayer> trafficControl = nodes.Get(0)->GetObject<TrafficControlLayer>();
    for (uint32_t index = 0; index < clientDevices.GetN(); ++index)
    {
        if (trafficControl->GetRootQueueDiscOnDevice(clientDevices.Get(index)))
        {
            trafficControl->DeleteRootQueueDiscOnDevice(clientDevices.Get(index));
        }
    }
    {
        std::ostringstream queueDepth;
        queueDepth << QUEUE_LIMIT_PACKETS << "p";
        TrafficControlHelper trafficControlHelper;
        trafficControlHelper.SetRootQueueDisc(
            "ns3::FifoQueueDisc",
            "MaxSize",
            QueueSizeValue(QueueSize(queueDepth.str())));
        trafficControlHelper.Install(clientDevices);
    }

    std::vector<Ipv4InterfaceContainer> interfaces;
    for (uint32_t index = 0; index < PATH_COUNT; ++index)
    {
        std::ostringstream subnet;
        subnet << "10.0." << index << ".0";
        Ipv4AddressHelper address;
        address.SetBase(subnet.str().c_str(), "255.255.255.0");
        interfaces.push_back(address.Assign(pathDevices[index]));
    }
    Ipv4GlobalRoutingHelper::PopulateRoutingTables();

    for (uint32_t index = 0; index < PATH_COUNT; ++index)
    {
        Ptr<RateErrorModel> errorModel = CreateObject<RateErrorModel>();
        errorModel->SetAttribute("ErrorRate", DoubleValue(PATHS[index].lossProbability));
        errorModel->SetAttribute("ErrorUnit", EnumValue(RateErrorModel::ERROR_UNIT_PACKET));
        // Drop on reception so queueing and transmission still consume link capacity,
        // matching the semantics of the Python model in validation/scenario_s1.py.
        pathDevices[index].Get(1)->SetAttribute("ReceiveErrorModel", PointerValue(errorModel));
    }

    Ptr<S1Sender> sender = CreateObject<S1Sender>();
    sender->Configure(handover,
                      interfaces[0].GetAddress(1),
                      interfaces[1].GetAddress(1));
    nodes.Get(0)->AddApplication(sender);
    sender->SetStartTime(Seconds(0.0));
    sender->SetStopTime(Seconds(DURATION_SECONDS));

    Ptr<S1Receiver> receiver = CreateObject<S1Receiver>();
    nodes.Get(1)->AddApplication(receiver);
    receiver->SetStartTime(Seconds(0.0));
    receiver->SetStopTime(Seconds(DURATION_SECONDS + 1.0));

    Simulator::Stop(Seconds(DURATION_SECONDS + 1.0));
    Simulator::Run();

    const double deliveryPercent =
        100.0 * static_cast<double>(receiver->receivedPackets) / static_cast<double>(sender->sentPackets);
    const double goodputMbps =
        static_cast<double>(receiver->receivedPackets) * PACKET_BYTES * 8.0 /
        (DURATION_SECONDS * 1e6);
    const double activePathsMean =
        sender->activePathSamples / static_cast<double>(sender->sentPackets);
    const double primarySharePercent =
        100.0 * static_cast<double>(sender->assignedPrimary) / static_cast<double>(sender->sentPackets);

    std::ofstream out;
    out.open(outputPath, append ? std::ios::app : std::ios::trunc);
    if (!out.is_open())
    {
        NS_FATAL_ERROR("Cannot open " << outputPath);
    }
    if (!append)
    {
        out << "scenario,policy,seed,packet_delivery_percent,one_way_delay_p95_ms,"
               "goodput_mbps,active_paths_mean,primary_share_percent\n";
    }
    out << scenario << ",capacity_weighted_swrr," << seed << "," << deliveryPercent << ","
        << Percentile95(receiver->delaysMs) << "," << goodputMbps << "," << activePathsMean << ","
        << primarySharePercent << "\n";
    out.close();

    std::printf("%s seed=%u sent=%llu received=%llu delivery=%.2f%% p95=%.2f ms\n",
                scenario.c_str(),
                seed,
                static_cast<unsigned long long>(sender->sentPackets),
                static_cast<unsigned long long>(receiver->receivedPackets),
                deliveryPercent,
                Percentile95(receiver->delaysMs));

    Simulator::Destroy();
    return 0;
}
