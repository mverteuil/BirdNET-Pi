"""Constants for BirdNET detections."""

# Model name to labels file mapping
# Simple dict since enum member names can't contain dots
MODEL_LABELS = {
    "BirdNET_GLOBAL_6K_V2.4_Model_FP16": "BirdNET_GLOBAL_6K_V2.4_Labels.txt",
    "BirdNET_6K_GLOBAL_MODEL": "BirdNET_GLOBAL_6K_V2.4_Labels.txt",
}

# Non-bird sounds from the BirdNET model that should be filtered out
# These are identified by having the same name before and after underscore
NON_BIRD_LABELS = {
    "Dog_Dog",
    "Engine_Engine",
    "Environmental_Environmental",
    "Fireworks_Fireworks",
    "Gun_Gun",
    "Human non-vocal_Human non-vocal",
    "Human vocal_Human vocal",
    "Human whistle_Human whistle",
    "Noise_Noise",
    "Power tools_Power tools",
    "Siren_Siren",
    # Cricket species - not birds but actual species names
    "Gryllus assimilis_Gryllus assimilis",
    "Miogryllus saussurei_Miogryllus saussurei",
}
