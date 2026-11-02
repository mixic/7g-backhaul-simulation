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
 * IPv4 versus IPv6 for the role-fluid / name fabric (docs/ip46-services.md).
 *
 * Three experiments over a single dual-stack point-to-point link, with the
 * standard IP stacks (not the PacketSocket fabric):
 *
 *   overhead   - fixed-size name-bearing datagrams; measures the on-wire bytes
 *                and goodput for the same application payload over each family.
 *   fragment   - a link MTU smaller than the payload; IPv4 fragments at the
 *                host, IPv6 drops and (if the stack supports it) signals
 *                Packet Too Big. Delivery and recovery are compared.
 *   agnostic   - a name-identified service reachable over both families; the
 *                client switches family mid-session and the interruption is
 *                measured (the "IPv6-agnostic service" concept).
 */

#include "ns3/core-module.h"
#include "ns3/network-module.h"
#include "ns3/internet-module.h"
#include "ns3/point-to-point-module.h"
#include "ns3/applications-module.h"
#include "ns3/packet-socket-factory.h"

#include <cstdint>
#include <cstdio>
#include <cstring>
#include <fstream>
#include <vector>

using namespace ns3;

namespace
{
struct Header
{
    uint32_t seq;
    uint64_t name;
    double sendTime;
    uint16_t family; // 4 or 6
};

uint64_t wireBytes = 0;

void
PhyTxEnd(Ptr<const Packet> packet)
{
    wireBytes += packet->GetSize();
}

class ClientApp : public Application
{
  public:
    static TypeId GetTypeId()
    {
        static TypeId tid = TypeId("ClientApp").SetParent<Application>().AddConstructor<ClientApp>();
        return tid;
    }

    std::string family{"ipv4"};
    std::string experiment{"overhead"};
    double rate{1000.0};
    uint32_t count{2000};
    uint32_t payloadBytes{128};
    Ipv4Address serverV4;
    Ipv6Address serverV6;
    double switchAt{5.0};
    double duration{10.0};

    uint64_t sent{0};
    uint64_t echoed{0};
    double rttSumMs{0.0};
    uint64_t rttSamples{0};
    double firstEchoTime{0.0};
    double firstV6EchoTime{0.0};
    double lastV4EchoTime{0.0};
    double switchGapMs{0.0};
    std::vector<double> rttsV4;
    std::vector<double> rttsV6;

  private:
    void StartApplication() override
    {
        m_socketV4 = Socket::CreateSocket(GetNode(), UdpSocketFactory::GetTypeId());
        m_socketV6 = Socket::CreateSocket(GetNode(), UdpSocketFactory::GetTypeId());
        m_socketV4->Connect(InetSocketAddress(serverV4, 9000));
        m_socketV6->Connect(Inet6SocketAddress(serverV6, 9000));
        m_socketV4->SetRecvCallback(MakeCallback(&ClientApp::OnEcho, this));
        m_socketV6->SetRecvCallback(MakeCallback(&ClientApp::OnEcho, this));
        for (uint32_t index = 0; index < count; ++index)
        {
            Simulator::Schedule(Seconds(index / rate), &ClientApp::SendOne, this, index);
        }
    }

    void StopApplication() override
    {
        if (m_socketV4)
        {
            m_socketV4->Close();
        }
        if (m_socketV6)
        {
            m_socketV6->Close();
        }
    }

    std::string FamilyFor(double now) const
    {
        if (experiment == "agnostic")
        {
            return now < switchAt ? "ipv4" : "ipv6";
        }
        return family;
    }

    void SendOne(uint32_t sequence)
    {
        const double now = Simulator::Now().GetSeconds();
        const std::string activeFamily = FamilyFor(now);
        const bool useV6 = activeFamily == "ipv6";
        Header header{sequence, 0xdeadbeefcafef00dULL, now,
                      static_cast<uint16_t>(useV6 ? 6 : 4)};
        std::vector<uint8_t> buffer(payloadBytes, 0);
        std::memcpy(buffer.data(), &header, sizeof(header));
        Ptr<Socket> socket = useV6 ? m_socketV6 : m_socketV4;
        if (useV6)
        {
            m_socketV6->Send(buffer.data(), payloadBytes, 0);
        }
        else
        {
            m_socketV4->Send(buffer.data(), payloadBytes, 0);
        }
        ++sent;
    }

    void OnEcho(Ptr<Socket> socket)
    {
        while (Ptr<Packet> packet = socket->Recv())
        {
            if (packet->GetSize() < sizeof(Header))
            {
                continue;
            }
            uint8_t buffer[2048];
            packet->CopyData(buffer, sizeof(Header));
            Header header;
            std::memcpy(&header, buffer, sizeof(header));
            const double now = Simulator::Now().GetSeconds();
            const double rtt = 1000.0 * (now - header.sendTime);
            rttSumMs += rtt;
            ++rttSamples;
            ++echoed;
            if (header.family == 6)
            {
                rttsV6.push_back(rtt);
                if (firstV6EchoTime == 0.0)
                {
                    firstV6EchoTime = now;
                }
            }
            else
            {
                rttsV4.push_back(rtt);
                lastV4EchoTime = now;
            }
        }
    }

    Ptr<Socket> m_socketV4;
    Ptr<Socket> m_socketV6;
};

class ServerApp : public Application
{
  public:
    static TypeId GetTypeId()
    {
        static TypeId tid = TypeId("ServerApp").SetParent<Application>().AddConstructor<ServerApp>();
        return tid;
    }

    uint64_t received{0};
    uint64_t bytesReceived{0};

  private:
    void StartApplication() override
    {
        m_socketV4 = Socket::CreateSocket(GetNode(), UdpSocketFactory::GetTypeId());
        m_socketV4->Bind(InetSocketAddress(Ipv4Address::GetAny(), 9000));
        m_socketV4->SetRecvCallback(MakeCallback(&ServerApp::OnPacket, this));
        m_socketV6 = Socket::CreateSocket(GetNode(), UdpSocketFactory::GetTypeId());
        m_socketV6->Bind(Inet6SocketAddress(Ipv6Address::GetAny(), 9000));
        m_socketV6->SetRecvCallback(MakeCallback(&ServerApp::OnPacket, this));
    }

    void OnPacket(Ptr<Socket> socket)
    {
        Address from;
        while (Ptr<Packet> packet = socket->RecvFrom(from))
        {
            ++received;
            bytesReceived += packet->GetSize();
            // Echo the whole datagram so the client can measure RTT.
            socket->SendTo(packet, 0, from);
        }
    }

    void StopApplication() override
    {
        if (m_socketV4)
        {
            m_socketV4->Close();
        }
        if (m_socketV6)
        {
            m_socketV6->Close();
        }
    }

    Ptr<Socket> m_socketV4;
    Ptr<Socket> m_socketV6;
};
} // namespace

int
main(int argc, char* argv[])
{
    std::string family = "ipv4";
    std::string experiment = "overhead";
    std::string out = "ip46.csv";
    uint32_t mtu = 1500;
    uint32_t payload = 128;

    CommandLine cmd(__FILE__);
    cmd.AddValue("family", "ipv4 or ipv6 (agnostic ignores this)", family);
    cmd.AddValue("experiment", "overhead|fragment|agnostic", experiment);
    cmd.AddValue("out", "CSV output path", out);
    cmd.AddValue("mtu", "link MTU for the fragment experiment", mtu);
    cmd.AddValue("payload", "application payload bytes", payload);
    cmd.Parse(argc, argv);

    NodeContainer nodes;
    nodes.Create(2);

    PointToPointHelper p2p;
    p2p.SetDeviceAttribute("DataRate", StringValue("1Gbps"));
    p2p.SetChannelAttribute("Delay", StringValue("1ms"));
    p2p.SetDeviceAttribute("Mtu", UintegerValue(mtu));
    NetDeviceContainer devices = p2p.Install(nodes.Get(0), nodes.Get(1));

    InternetStackHelper internet;
    internet.Install(nodes);

    Ipv4AddressHelper ipv4;
    ipv4.SetBase("10.0.0.0", "255.255.255.0");
    Ipv4InterfaceContainer i4 = ipv4.Assign(devices);

    Ipv6AddressHelper ipv6;
    ipv6.SetBase("2001:db8::", Ipv6Prefix(64));
    Ipv6InterfaceContainer i6 = ipv6.Assign(devices);

    Config::ConnectWithoutContext("/NodeList/0/DeviceList/0/PhyTxEnd", MakeCallback(&PhyTxEnd));

    Ptr<ClientApp> client = CreateObject<ClientApp>();
    client->family = family;
    client->experiment = experiment;
    client->serverV4 = i4.GetAddress(1);
    client->payloadBytes = payload;
    client->serverV6 = i6.GetAddress(1, 1);
    nodes.Get(0)->AddApplication(client);
    client->SetStartTime(Seconds(0.0));

    Ptr<ServerApp> server = CreateObject<ServerApp>();
    nodes.Get(1)->AddApplication(server);
    server->SetStartTime(Seconds(0.0));

    double duration = experiment == "agnostic" ? 10.0 : 3.0;
    client->duration = duration;
    // Spread the datagrams evenly across the whole run so the agnostic
    // experiment sends ~count/2 over IPv4 (before switchAt) and ~count/2 over
    // IPv6 (after switchAt), instead of exhausting the send budget early.
    client->rate = static_cast<double>(client->count) / duration;
    client->SetStopTime(Seconds(duration));
    server->SetStopTime(Seconds(duration));
    Simulator::Stop(Seconds(duration));
    Simulator::Run();

    const double goodput = server->bytesReceived * 8.0 / duration / 1e6; // Mbit/s
    const double overheadBytesPerPacket =
        wireBytes > 0 && client->sent > 0
            ? static_cast<double>(wireBytes) / client->sent - client->payloadBytes
            : 0.0;
    const double rttMean = client->rttSamples ? client->rttSumMs / client->rttSamples : 0.0;
    if (experiment == "agnostic" && client->firstV6EchoTime > 0.0 && client->lastV4EchoTime > 0.0)
    {
        client->switchGapMs = 1000.0 * (client->firstV6EchoTime - client->lastV4EchoTime);
    }

    std::ofstream csv(out, std::ios::app);
    const bool fresh = std::ifstream(out).peek() == std::ifstream::traits_type::eof();
    if (fresh)
    {
        csv << "experiment,family,mtu,sent,received,echoed,echoed_v4,echoed_v6,goodput_mbps,"
               "overhead_bytes_per_packet,rtt_mean_ms,switch_gap_ms\n";
    }
    csv << experiment << "," << family << "," << mtu << "," << client->sent << ","
        << server->received << "," << client->echoed << ","
        << client->rttsV4.size() << "," << client->rttsV6.size() << "," << goodput << ","
        << overheadBytesPerPacket << "," << rttMean << "," << client->switchGapMs << "\n";
    csv.close();

    std::printf("%s/%s mtu=%u sent=%llu received=%llu echoed=%llu goodput=%.2f "
                "overhead=%.1fB rtt=%.2fms\n",
                experiment.c_str(), family.c_str(), mtu,
                static_cast<unsigned long long>(client->sent),
                static_cast<unsigned long long>(server->received),
                static_cast<unsigned long long>(client->echoed),
                goodput, overheadBytesPerPacket, rttMean);

    Simulator::Destroy();
    return 0;
}
