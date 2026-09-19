#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Comprehensive scientific visualization suite for Firefield research results.

Generates 8 mandatory and 2 optional publication-grade figures:
1. (필수) Crosswind vs. Sensor Latency Max Position Error Heatmap
2. (필수) Flight Dynamics Time-Series & Error Comparisons by Method (M1~M5)
3. (필수) FDS Fire CFD HRR, Heat Flux, and Gas Temperature Time-Series
4. (필수) Distance, Wind, and Extinguisher Power vs. Suppression Efficiency Contour
5. (필수) 2D/3D Drone Rotor Wake, Fire Plume, and Suppression Field Coupling
6. (필수) Normalized Radar Chart and Bar Comparison across 5 Key Metrics
7. (필수) Single & Combined Operation Complementary Synergy Matrix Heatmap
8. (필수) Multi-Track Mission Timeline Dashboard (Detection -> Return)
9. (선택) Fire Scale, Wind Speed, Distance vs. Extinction Phase Map
10. (선택) Integrated 3D Operational Feasibility Surface & Contour Map
"""

import sys
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.vis_modules import (
    part1_heatmap,
    part2_flight,
    part3_fire_cfd,
    part4_contour,
    part5_field,
    part6_radar,
    part7_matrix,
    part8_timeline,
    part9_phase,
    part10_surface,
)
from scripts.vis_modules.common import OUT_DIR

def main():
    print("======================================================================")
    print("Firefield 연구용 고해상도 시각화 파이프라인 가동 (10개 시각화 생성)")
    print("======================================================================")
    part1_heatmap.generate()
    part2_flight.generate()
    part3_fire_cfd.generate()
    part4_contour.generate()
    part5_field.generate()
    part6_radar.generate()
    part7_matrix.generate()
    part8_timeline.generate()
    part9_phase.generate()
    part10_surface.generate()
    print("======================================================================")
    print(f"전체 10개 시각화 생성 완료! 저장 위치: {OUT_DIR}")
    print("======================================================================")

if __name__ == "__main__":
    main()
