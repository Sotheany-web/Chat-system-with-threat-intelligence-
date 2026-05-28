"""
Simple Baseline YOLO11-Seg Training Script
==========================================
Trains a standard YOLO11-seg model using standard Ultralytics defaults.
No command-line arguments, no external config files — just pure, simple training.
"""

import torch
from ultralytics import YOLO

# 1. Load pretrained YOLO11s-seg model
model = YOLO("yolo11m-seg.pt")

# 2. Train baseline model with standard Ultralytics defaults
results = model.train(
    data="d:/master_program/project_implementation/data/seg_only_dataset/data.yaml",
    epochs=100,
    imgsz=640,
    batch=16,
    lr0=5e-4,
    lrf=0.001,
    device=0 if torch.cuda.is_available() else "cpu",
    project="d:/master_program/project_implementation/output/models/baseline_yolo11_seg/seg_only_dataset",
    name="train",
    exist_ok=True,
    plots=True
)
