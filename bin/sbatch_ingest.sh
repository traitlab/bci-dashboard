#!/bin/bash
#SBATCH --account=rrg-bengioy-ad
#SBATCH --cpus-per-task=2
#SBATCH --mem=4G
#SBATCH --time=12:00:00
#SBATCH --output=/scratch/%u/slurm-ingest-%j.out
#SBATCH --job-name=bci-ingest

module purge
module load StdEnv/2023 python/3.11 httpproxy

cd /scratch/$USER/bci-dashboard
source .venv/bin/activate

python predict/ingest_photos.py \
    --csv input/boxes/bci_images_for_plantnet_w_split.csv \
    --no-aggregate \
    --delay 0.5
