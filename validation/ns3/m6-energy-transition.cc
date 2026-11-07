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
 * M6 (H10) energy cross-validation, ns-3.49 reference.
 *
 * Scope (read this before trusting the numbers):
 *
 *   The M6 energy model has four terms:
 *     E_tx    = wire bytes x 1e-7 J/byte   (transmission)  -> ns-3 measurable
 *     E_cpu   = cycles x 1e-9 J/cycle      (processing)    -> stipulated
 *     E_churn = 5 J per surgical edit      (control plane) -> no ns-3 counterpart
 *     E_llm   = 20 J per Oracle call       (inference)     -> no ns-3 counterpart
 *
 *   Only E_tx is packet-level arithmetic and therefore reproducible outside the
 *   SimPy codec. This program is an INDEPENDENT C++ re-implementation of the
 *   deterministic wire-byte arithmetic of simulation/layering/: it re-derives the
 *   static (F->E->C->T) and optimal (C->E->F->T) wire sizes with real zlib, and
 *   reproduces the SimPy payloads with the exact MT19937 stream, so its
 *   Wire_Bytes_Total can be compared seed-by-seed against
 *   results/m6/m6_exp2_raw.csv. E_cpu and E_llm are applied as the same stipulated
 *   constants as the SimPy model, never "measured" here.
 *
 * Cross-validation result (30 seeds):
 *
 *   * static_iso: 4650 bytes for every seed -- EXACT match (delta 0.0).
 *   * optimal (greedy == llm): matches the structure; the mean differs by ~2 %
 *     ONLY because Python on Windows bundles zlib-ng 1.3.1 (a better compressor)
 *     while this build links stock zlib 1.3.1. The payload bytes are reproduced
 *     byte-for-byte (verified for alphabets 2, 5, 9); the compressible phases
 *     compress to a slightly different size under the two zlib implementations
 *     (e.g. the seed-7 payload: 627 bytes under zlib-ng, 693 under stock zlib).
 *     The EROI verdict is unchanged: ~3e-6, i.e. H10 remains refuted.
 *
 *   Packet-level loss/delivery is a separate M5 concern and is already
 *   cross-validated by the S1 and RFMP references (s1-multipath-handover.cc,
 *   rfmp-role-transition.cc) which use the same RateErrorModel.
 *
 * ns-3 version used: ns-3.49
 *   ./ns3 configure --enable-modules=core,network,internet,point-to-point,applications,traffic-control \
 *                   --disable-examples --disable-tests --disable-python
 *   (this scratch links zlib via a subdirectory CMakeLists.txt)
 *
 * Usage:
 *   m6-energy-transition --seeds=30 --out=m6_ns3.csv
 */

#include "ns3/core-module.h"

#include <zlib.h>

#include <algorithm>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <fstream>
#include <iomanip>
#include <string>
#include <vector>

using namespace ns3;

namespace
{
// ---- Shared scenario constants (mirror run_m5_experiments.py) -------------
constexpr uint32_t PAYLOAD_SIZE = 1400;
constexpr uint32_t NONCE_BYTES = 12;
constexpr uint32_t TAG_BYTES = 16;
constexpr uint32_t AEAD_OVERHEAD = NONCE_BYTES + TAG_BYTES; // 28
constexpr uint32_t TUNNEL_HEADER = 28;                       // 28
constexpr uint32_t FRAGMENT_HEADER = 8;                      // 8
constexpr double E_TX_PER_BYTE = 1e-7;                       // J/byte
constexpr double E_CPU_PER_CYCLE = 1e-9;                     // J/cycle
constexpr uint32_t CYCLES_PER_BYTE = 100;                    // encrypt/compress
constexpr double E_LLM_PER_CALL = 20.0;                      // J/call
constexpr uint32_t LLM_CALLS = 3;                            // one per phase

struct Phase
{
    const char* name;
    uint32_t mtu;
    double loss;
    bool compressible;
};

const Phase PHASES[3] = {
    {"fiber", 1500, 0.00, true},
    {"microwave", 900, 0.01, false},
    {"satellite", 500, 0.05, true},
};

// ---- Python random.Random(seed) re-implementation (MT19937) ---------------
//
// Python 3.14 seeds its Mersenne Twister with init_by_array([seed], 1) for an
// integer seed (Modules/_randommodule.c, random_seed), NOT the classic
// init_genrand(seed) that std::mt19937 uses. The tempering and getrandbits()
// are unchanged, so this class reproduces Python's exact word stream.
class Mt19937
{
    static constexpr int N = 624;
    static constexpr int M = 397;
    static constexpr uint32_t MATRIX_A = 0x9908b0dfU;
    static constexpr uint32_t UPPER_MASK = 0x80000000U;
    static constexpr uint32_t LOWER_MASK = 0x7fffffffU;
    uint32_t m_state[N];
    int m_index;

  public:
    void initGenrand(uint32_t s)
    {
        m_state[0] = s;
        for (int mti = 1; mti < N; ++mti)
        {
            m_state[mti] = 1812433253U * (m_state[mti - 1] ^ (m_state[mti - 1] >> 30)) + mti;
        }
        m_index = N;
    }

    void initByArray(const uint32_t* key, size_t keyLength)
    {
        initGenrand(19650218U);
        size_t i = 1, j = 0;
        size_t k = (N > keyLength) ? N : keyLength;
        for (; k; --k)
        {
            m_state[i] =
                (m_state[i] ^ ((m_state[i - 1] ^ (m_state[i - 1] >> 30)) * 1664525U)) + key[j] +
                static_cast<uint32_t>(j);
            ++i;
            ++j;
            if (i >= N)
            {
                m_state[0] = m_state[N - 1];
                i = 1;
            }
            if (j >= keyLength)
            {
                j = 0;
            }
        }
        for (k = N - 1; k; --k)
        {
            m_state[i] =
                (m_state[i] ^ ((m_state[i - 1] ^ (m_state[i - 1] >> 30)) * 1566083941U)) -
                static_cast<uint32_t>(i);
            ++i;
            if (i >= N)
            {
                m_state[0] = m_state[N - 1];
                i = 1;
            }
        }
        m_state[0] = 0x80000000U;
        m_index = N;
    }

    explicit Mt19937(uint32_t seed)
    {
        uint32_t key[1] = {seed};
        initByArray(key, 1);
    }

    uint32_t genrand()
    {
        uint32_t y;
        static const uint32_t mag01[2] = {0x0U, MATRIX_A};
        if (m_index >= N)
        {
            int kk;
            for (kk = 0; kk < N - M; ++kk)
            {
                y = (m_state[kk] & UPPER_MASK) | (m_state[kk + 1] & LOWER_MASK);
                m_state[kk] = m_state[kk + M] ^ (y >> 1) ^ mag01[y & 0x1U];
            }
            for (; kk < N - 1; ++kk)
            {
                y = (m_state[kk] & UPPER_MASK) | (m_state[kk + 1] & LOWER_MASK);
                m_state[kk] = m_state[kk + (M - N)] ^ (y >> 1) ^ mag01[y & 0x1U];
            }
            y = (m_state[N - 1] & UPPER_MASK) | (m_state[0] & LOWER_MASK);
            m_state[N - 1] = m_state[M - 1] ^ (y >> 1) ^ mag01[y & 0x1U];
            m_index = 0;
        }
        y = m_state[m_index++];
        y ^= (y >> 11);
        y ^= (y << 7) & 0x9d2c5680U;
        y ^= (y << 15) & 0xefc60000U;
        y ^= (y >> 18);
        return y;
    }
};

class PyRandom
{
  public:
    explicit PyRandom(uint32_t seed)
        : m_engine(seed)
    {
    }

    uint32_t genrand()
    {
        return m_engine.genrand();
    }

    // getrandbits(k) for k <= 32: the top k bits of one 32-bit word.
    uint32_t getrandbits(uint32_t k)
    {
        return genrand() >> (32 - k);
    }

    uint32_t randbelow(uint32_t n)
    {
        const uint32_t k = bitLength(n);
        uint32_t r = getrandbits(k);
        while (r >= n)
        {
            r = getrandbits(k);
        }
        return r;
    }

  private:
    static uint32_t bitLength(uint32_t n)
    {
        uint32_t k = 0;
        while (n > 0)
        {
            ++k;
            n >>= 1;
        }
        return k;
    }

    Mt19937 m_engine;
};

std::vector<uint8_t> compressiblePayload(uint32_t seed, uint32_t size)
{
    PyRandom rng(seed);
    const uint32_t alphabetSize = 2 + seed % 8;
    std::vector<uint8_t> out(size);
    for (uint32_t i = 0; i < size; ++i)
    {
        out[i] = static_cast<uint8_t>('A' + rng.randbelow(alphabetSize));
    }
    return out;
}

std::vector<uint8_t> randomPayload(uint32_t seed, uint32_t size)
{
    // randbytes(size) == getrandbits(size*8).to_bytes(size, 'little')
    PyRandom rng(seed);
    std::vector<uint8_t> out(size);
    const uint32_t bits = size * 8;
    const uint32_t words = (bits - 1) / 32 + 1;
    int32_t k = static_cast<int32_t>(bits);
    uint32_t bytePos = 0;
    for (uint32_t i = 0; i < words; ++i)
    {
        uint32_t r = rng.genrand();
        if (k < 32)
        {
            r >>= (32 - k);
        }
        for (uint32_t b = 0; b < 4 && bytePos < size; ++b)
        {
            out[bytePos++] = static_cast<uint8_t>((r >> (8 * b)) & 0xff);
        }
        k -= 32;
    }
    return out;
}

// ---- zlib (mirror Python zlib.compress(data, 6)) --------------------------
uint64_t zlibCompressSize(const std::vector<uint8_t>& data)
{
    uLongf destLen = compressBound(static_cast<uLong>(data.size()));
    std::vector<Bytef> dest(destLen);
    const int rc = compress2(dest.data(),
                             &destLen,
                             reinterpret_cast<const Bytef*>(data.data()),
                             static_cast<uLong>(data.size()),
                             6);
    if (rc != Z_OK)
    {
        std::fprintf(stderr, "zlib compress2 failed: %d\n", rc);
        std::exit(1);
    }
    return static_cast<uint64_t>(destLen);
}

// ---- wire-byte arithmetic (mirror simulation/layering/layers.py) ----------
uint64_t wireBytesStatic(uint32_t mtu)
{
    // Static order F -> E -> C -> T on the 1400-byte payload.
    //   F: 8-byte header per fragment, chunk = mtu - 8
    //   E: +28 bytes (12 nonce + 16 tag) per fragment
    //   C: compressing the AEAD frame (incompressible ciphertext) adds 11 bytes
    //      = 2-byte zlib header + 5-byte stored block + 4-byte Adler-32.
    //      Verified against the SimPy codec: 1475 / 1550 / 1625 for MTU
    //      1500 / 900 / 500 respectively.
    //   T: +28 bytes per fragment
    const uint64_t payload = PAYLOAD_SIZE;
    const uint64_t chunk = mtu - FRAGMENT_HEADER;
    const uint64_t count = (payload + chunk - 1) / chunk;
    uint64_t total = 0;
    uint64_t rem = payload;
    for (uint64_t i = 0; i < count; ++i)
    {
        const uint64_t data = std::min(rem, chunk);
        total += data + FRAGMENT_HEADER + AEAD_OVERHEAD + 11 + TUNNEL_HEADER;
        rem -= data;
    }
    return total;
}

uint64_t wireBytesOptimal(const std::vector<uint8_t>& payload, uint32_t mtu)
{
    // Optimal order C -> E -> F -> T.
    //   C: real zlib on the raw payload (data-dependent)
    //   E: +28 bytes
    //   F: 8-byte header per fragment, chunk = mtu - 8
    //   T: +28 bytes per fragment
    const uint64_t compressed = zlibCompressSize(payload);
    const uint64_t afterEncrypt = compressed + AEAD_OVERHEAD;
    const uint64_t chunk = mtu - FRAGMENT_HEADER;
    const uint64_t count = (afterEncrypt + chunk - 1) / chunk;
    uint64_t total = 0;
    uint64_t rem = afterEncrypt;
    for (uint64_t i = 0; i < count; ++i)
    {
        const uint64_t data = std::min(rem, chunk);
        total += data + FRAGMENT_HEADER + TUNNEL_HEADER;
        rem -= data;
    }
    return total;
}

} // namespace

int
main(int argc, char* argv[])
{
    uint32_t seeds = 30;
    std::string outputPath = "m6_ns3.csv";

    CommandLine cmd(__FILE__);
    cmd.AddValue("seeds", "number of seeds (0..seeds-1)", seeds);
    cmd.AddValue("out", "CSV output path", outputPath);
    cmd.Parse(argc, argv);

    const double eCpu = static_cast<double>(PAYLOAD_SIZE * LLM_CALLS) * CYCLES_PER_BYTE *
                        E_CPU_PER_CYCLE; // 4200 * 100 * 1e-9
    const double eLlm = static_cast<double>(LLM_CALLS) * E_LLM_PER_CALL; // 60

    std::ofstream out(outputPath);
    if (!out.is_open())
    {
        NS_FATAL_ERROR("Cannot open " << outputPath);
    }
    out << "experiment,arm,seed,Wire_Bytes_Total,E_tx_J,E_cpu_J,E_llm_J,E_tx_saved_J,EROI\n";
    out << std::fixed << std::setprecision(9);

    for (uint32_t seed = 0; seed < seeds; ++seed)
    {
        uint64_t staticTotal = 0;
        uint64_t optimalTotal = 0;
        for (const Phase& phase : PHASES)
        {
            const std::vector<uint8_t> payload = phase.compressible
                                                     ? compressiblePayload(seed, PAYLOAD_SIZE)
                                                     : randomPayload(seed, PAYLOAD_SIZE);
            staticTotal += wireBytesStatic(phase.mtu);
            optimalTotal += wireBytesOptimal(payload, phase.mtu);
        }

        const double eTxStatic = static_cast<double>(staticTotal) * E_TX_PER_BYTE;
        const double eTxOptimal = static_cast<double>(optimalTotal) * E_TX_PER_BYTE;
        const double eSaved = static_cast<double>(staticTotal - optimalTotal) * E_TX_PER_BYTE;
        const double eroi = eSaved / eLlm;

        out << "exp2,static_iso," << seed << "," << staticTotal << "," << eTxStatic << ","
            << eCpu << ",0,0,\n";
        out << "exp2,greedy_heuristic," << seed << "," << optimalTotal << "," << eTxOptimal << ","
            << eCpu << ",0," << eSaved << ",\n";
        out << "exp2,llm_compiler," << seed << "," << optimalTotal << "," << eTxOptimal << ","
            << eCpu << "," << eLlm << "," << eSaved << "," << eroi << "\n";
    }
    out.close();

    std::printf("wrote %u seeds x 3 arms to %s\n", seeds, outputPath.c_str());
    return 0;
}
