
#include <array>
#include <bit>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <limits>
using uint = std::uint32_t;
uint PackU8F32(uint bits, uint index, uint old) {
  uint byteValue = 0u;
  // De 0,5 exclu à +infini inclus : les autres valeurs donnent zéro.
  if (bits > 0x3F000000u && bits <= 0x7F800000u) {
    if (bits >= 0x437F0000u) {
      byteValue = 255u;
    } else {
      // En deçà de 255, le décalage vaut 16 à 24. L'arrondi reste entier.
      uint drop = 150u - (bits >> 23);
      uint significand = (bits & 0x007FFFFFu) | 0x00800000u;
      uint whole = significand >> drop;
      uint fraction = significand & ((1u << drop) - 1u);
      uint halfway = 1u << (drop - 1u);
      byteValue = whole + (fraction > halfway || (fraction == halfway && (whole & 1u) != 0u) ? 1u : 0u);
    }
  }
  uint shift = (index & 3u) * 8u;
  return (old & ~(0xFFu << shift)) | (byteValue << shift);
}

int main() {
  constexpr uint old = 0xaabbccddu;
  constexpr std::array<uint, 8> indexes{0, 1, 2, 3, 4, 6, 7, 0xffffffffu};
  unsigned checked = 0;
  auto check = [&](uint input) {
    const auto value = std::bit_cast<float>(input);
    uint rounded = 0;
    if (value >= 255.0f) {
      rounded = 255;
    } else if (value > 0.0f) {
      rounded = static_cast<uint>(std::nearbyint(value));
    }
    for (uint index : indexes) {
      const uint shift = 8 * (index % 4);
      const uint expected = (old & ~(255u << shift)) | (rounded << shift);
      const uint actual = PackU8F32(input, index, old);
      if (actual != expected) {
        std::printf("mismatch: input=%08x index=%u actual=%08x expected=%08x\n",
                    input, index, actual, expected);
        return false;
      }
      ++checked;
    }
    return true;
  };
  for (int n = -2; n <= 257; ++n) {
    const float halfway = static_cast<float>(n) + 0.5f;
    const float infinity = std::numeric_limits<float>::infinity();
    for (float edge : {std::nextafter(halfway, -infinity), halfway,
                       std::nextafter(halfway, infinity)}) {
      if (!check(std::bit_cast<uint>(edge))) return 1;
    }
  }
  for (uint input : {0u, 0x80000000u, 1u, 0x80000001u, 0x007fffffu,
                     0x7f800000u, 0xff800000u, 0x7f800001u, 0x7fc00011u}) {
    if (!check(input)) return 1;
  }
  uint state = 0x13e3f1c5u;
  for (int n = 0; n < 16384; ++n) {
    state ^= state << 13;
    state ^= state >> 17;
    state ^= state << 5;
    if (!check(state)) return 1;
  }
  std::printf("pack_helper_cpu_checks=%u\n", checked);
}
