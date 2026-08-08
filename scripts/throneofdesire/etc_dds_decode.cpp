// Decode X-Legend DDS files with the custom ETC2/ETCA/EAC4 FourCC values.
//
// Build this file together with Ericsson ETCPACK's unmodified etcdec.cxx.
// The output is an uncompressed 32-bit, top-left-origin TGA image.

#include <algorithm>
#include <cctype>
#include <cmath>
#include <cstdint>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>

void decompressBlockETC2(unsigned int, unsigned int, unsigned char*, int, int, int, int);
void decompressBlockAlpha(unsigned char*, unsigned char*, int, int, int, int);
void decompressBlockAlpha16bit(unsigned char*, unsigned char*, int, int, int, int);
extern int formatSigned;

static std::vector<unsigned char> read_file(const char* path) {
    std::ifstream stream(path, std::ios::binary | std::ios::ate);
    if (!stream) {
        throw std::runtime_error(std::string("cannot open input: ") + path);
    }
    const std::streamsize size = stream.tellg();
    stream.seekg(0, std::ios::beg);
    std::vector<unsigned char> data(static_cast<std::size_t>(size));
    if (size && !stream.read(reinterpret_cast<char*>(data.data()), size)) {
        throw std::runtime_error(std::string("cannot read input: ") + path);
    }
    return data;
}

static std::uint32_t read_u32(const std::vector<unsigned char>& data, std::size_t offset) {
    if (offset + 4 > data.size()) {
        throw std::runtime_error("truncated DDS header");
    }
    return static_cast<std::uint32_t>(data[offset]) |
           (static_cast<std::uint32_t>(data[offset + 1]) << 8) |
           (static_cast<std::uint32_t>(data[offset + 2]) << 16) |
           (static_cast<std::uint32_t>(data[offset + 3]) << 24);
}

static std::uint32_t read_be_u32(const unsigned char* data) {
    return (static_cast<std::uint32_t>(data[0]) << 24) |
           (static_cast<std::uint32_t>(data[1]) << 16) |
           (static_cast<std::uint32_t>(data[2]) << 8) |
           static_cast<std::uint32_t>(data[3]);
}

static void write_tga(
    const char* path,
    const std::vector<unsigned char>& rgba,
    unsigned width,
    unsigned height,
    unsigned stride) {
    if (width > 65535 || height > 65535) {
        throw std::runtime_error("TGA dimensions exceed 65535");
    }
    unsigned char header[18] = {};
    header[2] = 2;
    header[12] = static_cast<unsigned char>(width & 0xff);
    header[13] = static_cast<unsigned char>(width >> 8);
    header[14] = static_cast<unsigned char>(height & 0xff);
    header[15] = static_cast<unsigned char>(height >> 8);
    header[16] = 32;
    header[17] = 0x28;

    std::ofstream stream(path, std::ios::binary);
    if (!stream) {
        throw std::runtime_error(std::string("cannot open output: ") + path);
    }
    stream.write(reinterpret_cast<const char*>(header), sizeof(header));
    for (unsigned y = 0; y < height; ++y) {
        for (unsigned x = 0; x < width; ++x) {
            const unsigned char* pixel = &rgba[4 * (x + y * stride)];
            const unsigned char bgra[4] = {pixel[2], pixel[1], pixel[0], pixel[3]};
            stream.write(reinterpret_cast<const char*>(bgra), sizeof(bgra));
        }
    }
    if (!stream) {
        throw std::runtime_error(std::string("cannot write output: ") + path);
    }
}

int main(int argc, char** argv) {
    if (argc != 3) {
        std::cerr << "usage: etc_dds_decode INPUT.dds OUTPUT.tga\n";
        return 2;
    }
    try {
        const std::vector<unsigned char> data = read_file(argv[1]);
        if (data.size() < 128 || std::string(
                reinterpret_cast<const char*>(data.data()), 4) != "DDS ") {
            throw std::runtime_error("input is not a DDS file");
        }
        const unsigned height = read_u32(data, 12);
        const unsigned width = read_u32(data, 16);
        const std::string fourcc(reinterpret_cast<const char*>(&data[84]), 4);
        const unsigned padded_width = (width + 3) & ~3U;
        const unsigned padded_height = (height + 3) & ~3U;
        const unsigned blocks_x = padded_width / 4;
        const unsigned blocks_y = padded_height / 4;
        const unsigned bytes_per_block = fourcc == "ETC2" ? 8 : 16;
        const std::size_t required =
            128ULL + static_cast<std::size_t>(blocks_x) * blocks_y * bytes_per_block;
        if (fourcc != "ETC2" && fourcc != "ETCA" && fourcc != "EAC4") {
            throw std::runtime_error("unsupported X-Legend FourCC: " + fourcc);
        }
        if (data.size() < required) {
            throw std::runtime_error("DDS top mip is truncated");
        }

        std::vector<unsigned char> rgb(3ULL * padded_width * padded_height, 0);
        std::vector<unsigned char> alpha(padded_width * padded_height, 255);
        std::vector<unsigned char> red16(2ULL * padded_width * padded_height, 0);
        std::vector<unsigned char> green16(2ULL * padded_width * padded_height, 0);
        std::size_t offset = 128;
        formatSigned = 0;
        for (unsigned by = 0; by < blocks_y; ++by) {
            for (unsigned bx = 0; bx < blocks_x; ++bx) {
                const int x = static_cast<int>(bx * 4);
                const int y = static_cast<int>(by * 4);
                if (fourcc == "ETCA") {
                    decompressBlockAlpha(
                        const_cast<unsigned char*>(&data[offset]),
                        alpha.data(), padded_width, padded_height, x, y);
                    decompressBlockETC2(
                        read_be_u32(&data[offset + 8]),
                        read_be_u32(&data[offset + 12]),
                        rgb.data(), padded_width, padded_height, x, y);
                } else if (fourcc == "ETC2") {
                    decompressBlockETC2(
                        read_be_u32(&data[offset]),
                        read_be_u32(&data[offset + 4]),
                        rgb.data(), padded_width, padded_height, x, y);
                } else {
                    decompressBlockAlpha16bit(
                        const_cast<unsigned char*>(&data[offset]),
                        red16.data(), padded_width, padded_height, x, y);
                    decompressBlockAlpha16bit(
                        const_cast<unsigned char*>(&data[offset + 8]),
                        green16.data(), padded_width, padded_height, x, y);
                }
                offset += bytes_per_block;
            }
        }

        std::vector<unsigned char> rgba(4ULL * padded_width * padded_height, 255);
        std::string input_name(argv[1]);
        std::transform(input_name.begin(), input_name.end(), input_name.begin(), ::tolower);
        const bool is_normal_map = input_name.find("_normal.dds") != std::string::npos;
        for (std::size_t i = 0; i < static_cast<std::size_t>(padded_width) * padded_height; ++i) {
            if (fourcc == "EAC4") {
                const unsigned r16 = static_cast<unsigned>(red16[2 * i]) |
                                     (static_cast<unsigned>(red16[2 * i + 1]) << 8);
                const unsigned g16 = static_cast<unsigned>(green16[2 * i]) |
                                     (static_cast<unsigned>(green16[2 * i + 1]) << 8);
                const float nx = static_cast<float>(r16) / 32767.5f - 1.0f;
                const float ny = static_cast<float>(g16) / 32767.5f - 1.0f;
                const float nz = std::sqrt(std::max(0.0f, 1.0f - nx * nx - ny * ny));
                rgba[4 * i] = static_cast<unsigned char>(r16 >> 8);
                rgba[4 * i + 1] = static_cast<unsigned char>(g16 >> 8);
                rgba[4 * i + 2] = static_cast<unsigned char>(std::min(255.0f, (nz * 0.5f + 0.5f) * 255.0f));
            } else {
                rgba[4 * i] = rgb[3 * i];
                rgba[4 * i + 1] = rgb[3 * i + 1];
                if (is_normal_map) {
                    const float nx = static_cast<float>(rgb[3 * i]) / 127.5f - 1.0f;
                    const float ny = static_cast<float>(rgb[3 * i + 1]) / 127.5f - 1.0f;
                    const float nz = std::sqrt(std::max(0.0f, 1.0f - nx * nx - ny * ny));
                    rgba[4 * i + 2] = static_cast<unsigned char>(
                        std::min(255.0f, (nz * 0.5f + 0.5f) * 255.0f));
                } else {
                    rgba[4 * i + 2] = rgb[3 * i + 2];
                }
                rgba[4 * i + 3] = alpha[i];
            }
        }
        write_tga(argv[2], rgba, width, height, padded_width);
        std::cerr << fourcc << " " << width << "x" << height << " -> " << argv[2] << "\n";
        return 0;
    } catch (const std::exception& exc) {
        std::cerr << "error: " << exc.what() << "\n";
        return 2;
    }
}
