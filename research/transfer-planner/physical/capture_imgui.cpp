// SPDX-License-Identifier: MIT
#include "imgui.h"

#include <algorithm>
#include <cstdint>
#include <cstring>
#include <iostream>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

using Bytes = std::vector<std::uint8_t>;

struct Geometry {
    Bytes vertices;
    Bytes indices;
};

void append(Bytes& bytes, const void* source, std::size_t size) {
    const auto start = bytes.size();
    bytes.resize(start + size);
    if (size) {
        std::memcpy(bytes.data() + start, source, size);
    }
}

std::vector<Geometry> capture(bool interactive) {
    ImGui::CreateContext();
    auto& io = ImGui::GetIO();
    io.IniFilename = nullptr;
    io.LogFilename = nullptr;
    io.DisplaySize = ImVec2(1280.0F, 720.0F);
    io.DeltaTime = 1.0F / 60.0F;
    io.BackendFlags |= ImGuiBackendFlags_RendererHasVtxOffset;
    unsigned char* font = nullptr;
    int width = 0;
    int height = 0;
    io.Fonts->GetTexDataAsRGBA32(&font, &width, &height);

    std::vector<Geometry> result;
    for (int i = -4; i <= 180; ++i) {
        ImGui::NewFrame();
        ImGui::SetNextWindowPos(ImVec2(40.0F, 30.0F), ImGuiCond_Once);
        ImGui::SetNextWindowSize(ImVec2(600.0F, 300.0F), ImGuiCond_Always);
        ImGui::ShowDemoWindow();
        ImGui::SetNextWindowPos(ImVec2(650.0F, 30.0F), ImGuiCond_Once);
        ImGui::SetNextWindowSize(ImVec2(560.0F, 360.0F), ImGuiCond_Always);
        if (interactive && i >= 0) {
            const auto step = i / 6;
            const auto offset = step < 15 ? step : 30 - step;
            ImGui::SetNextWindowScroll(ImVec2(-1.0F, 19.0F * static_cast<float>(offset)));
        }
        if (ImGui::Begin("Asset list")) {
            ImGuiListClipper clipper;
            clipper.Begin(100);
            while (clipper.Step()) {
                for (int row = clipper.DisplayStart; row < clipper.DisplayEnd; ++row) {
                    ImGui::Text("Asset %03d  |  %d vertices  |  %s", row, 100 + row * 37,
                                row % 5 == 0 ? "building" : "ready");
                }
            }
        }
        ImGui::End();
        ImGui::Render();
        if (i < 0) {
            continue;
        }
        const auto* draw = ImGui::GetDrawData();
        if (!draw || draw->TotalVtxCount <= 0 || draw->TotalIdxCount <= 0) {
            throw std::runtime_error("Dear ImGui demo emitted no geometry");
        }
        Geometry geometry;
        for (int j = 0; j < draw->CmdListsCount; ++j) {
            const auto& list = *draw->CmdLists[j];
            append(geometry.vertices, list.VtxBuffer.Data,
                   static_cast<std::size_t>(list.VtxBuffer.Size) * sizeof(ImDrawVert));
            append(geometry.indices, list.IdxBuffer.Data,
                   static_cast<std::size_t>(list.IdxBuffer.Size) * sizeof(ImDrawIdx));
        }
        result.push_back(std::move(geometry));
    }
    ImGui::DestroyContext();
    return result;
}

void emit(const std::string& name, std::vector<Geometry>& frames, Bytes Geometry::*field) {
    constexpr std::size_t atom = 64;
    std::size_t largest = 0;
    for (auto& frame : frames) {
        largest = std::max(largest, (frame.*field).size());
    }
    const auto extent = (largest + atom - 1) / atom;
    for (auto& frame : frames) {
        (frame.*field).resize(extent * atom, 0);
    }
    std::cout << "case " << name << ' ' << extent << ' ' << extent << "\nallow 0 " << extent << '\n';
    for (std::size_t i = 1; i < frames.size(); ++i) {
        const auto& before = frames[i - 1].*field;
        const auto& after = frames[i].*field;
        std::cout << "frame " << i << '\n';
        std::size_t first = 0;
        while (first < extent) {
            const auto dirty = [&](std::size_t item) {
                return std::memcmp(before.data() + item * atom, after.data() + item * atom, atom) != 0;
            };
            if (!dirty(first)) {
                ++first;
                continue;
            }
            auto end = first + 1;
            while (end < extent && dirty(end)) {
                ++end;
            }
            std::cout << "dirty " << first << ' ' << end << '\n';
            first = end;
        }
        std::cout << "endframe\n";
    }
    std::cout << "endcase\n";
}

int main() {
    std::cout << "PBTRACE1 64\n";
    for (bool interactive : {false, true}) {
        auto frames = capture(interactive);
        const std::string label = interactive ? "imgui_scrolling" : "imgui_idle";
        emit(label + "_vertices", frames, &Geometry::vertices);
        emit(label + "_indices", frames, &Geometry::indices);
    }
}
