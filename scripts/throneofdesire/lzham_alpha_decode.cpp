// Decode the raw LZHAM Alpha8 streams used by X-Legend textures.
//
// Build this file together with richgel999/lzham_alpha's lzhamdecomp sources.
// Usage: lzham_alpha_decode INPUT OUTPUT EXPECTED_SIZE

#include <algorithm>
#include <cstdlib>
#include <fstream>
#include <iostream>
#include <string>
#include <vector>

#include "lzham.h"
#include "lzham_decomp.h"

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

static void write_file(const char* path, const std::vector<unsigned char>& data) {
    std::ofstream stream(path, std::ios::binary);
    if (!stream || !stream.write(
            reinterpret_cast<const char*>(data.data()),
            static_cast<std::streamsize>(data.size()))) {
        throw std::runtime_error(std::string("cannot write output: ") + path);
    }
}

int main(int argc, char** argv) {
    if (argc != 4) {
        std::cerr << "usage: lzham_alpha_decode INPUT OUTPUT EXPECTED_SIZE\n";
        return 2;
    }
    try {
        const std::vector<unsigned char> input = read_file(argv[1]);
        const std::size_t expected_size = static_cast<std::size_t>(
            std::strtoull(argv[3], NULL, 0));
        if (!expected_size) {
            throw std::runtime_error("EXPECTED_SIZE must be positive");
        }

        static const unsigned char kXLegendMagic[5] = {
            0x7f, 0x64, 0x01, 0x15, 0x12
        };
        std::size_t input_offset = 0;
        if (input.size() >= sizeof(kXLegendMagic) &&
            std::equal(kXLegendMagic, kXLegendMagic + sizeof(kXLegendMagic),
                       input.begin())) {
            input_offset = sizeof(kXLegendMagic);
        }
        if (input_offset == input.size()) {
            throw std::runtime_error("input contains only the X-Legend magic");
        }

        const std::size_t compressed_size = input.size() - input_offset;
        if (compressed_size > 0xffffffffU) {
            throw std::runtime_error("compressed input is too large");
        }

        lzham_z_stream stream = {};
        stream.next_in = input.data() + input_offset;
        stream.avail_in = static_cast<unsigned int>(compressed_size);
        int status = lzham::lzham_lib_z_inflateInit2(&stream, -15);
        if (status != LZHAM_Z_OK) {
            throw std::runtime_error("lzham inflateInit2(-15) failed");
        }

        std::vector<unsigned char> output;
        output.reserve(expected_size);
        unsigned char chunk[16384];
        while (true) {
            const unsigned int previous_input = stream.avail_in;
            stream.next_out = chunk;
            stream.avail_out = sizeof(chunk);
            status = lzham::lzham_lib_z_inflate(&stream, LZHAM_Z_NO_FLUSH);
            const std::size_t produced = sizeof(chunk) - stream.avail_out;
            output.insert(output.end(), chunk, chunk + produced);

            if (status == LZHAM_Z_STREAM_END) {
                break;
            }
            if (status != LZHAM_Z_OK && status != LZHAM_Z_BUF_ERROR) {
                lzham::lzham_lib_z_inflateEnd(&stream);
                std::cerr << "inflate failed: status=" << status
                          << " input_left=" << stream.avail_in
                          << " output=" << output.size() << "\n";
                return 1;
            }
            if (!produced && previous_input == stream.avail_in) {
                break;
            }
        }
        lzham::lzham_lib_z_inflateEnd(&stream);
        std::cerr << "status=" << status
                  << " input_used=" << stream.total_in
                  << " output=" << output.size() << "\n";
        write_file(argv[2], output);
        return 0;
    } catch (const std::exception& exc) {
        std::cerr << "error: " << exc.what() << "\n";
        return 2;
    }
}
