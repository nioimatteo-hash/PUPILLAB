# PupilLab

**PupilLab** is a research software prototype developed for the standardized manual measurement of the **Pupil-to-Iris Ratio (PIR)** in postmortem eyes.

The software was designed to provide a simple, transparent and reproducible workflow for manual pupillary measurements from digital ocular photographs and to support research in forensic ophthalmology and postmortem pupillometry.

---

## Current Version

**Version:** 0.6.1 (Private Beta)

Current release status:

- Private repository
- Research prototype
- Under active development

---

## Main Features

- Manual two-point linear measurement of pupil diameter
- Manual two-point linear measurement of iris diameter
- Automatic Pupil-to-Iris Ratio (PIR) calculation
- Five-category PIR classification
- Bilateral image loading with automatic splitting
- Separate management of right (OD) and left (OS) eyes
- Annotated image generation
- CSV export
- Excel export
- PDF report generation
- Exploratory statistical analysis
- Publication-quality graphical outputs
- Italian and English interface

---

## Scientific Background

PupilLab has been developed to support standardized postmortem pupillometry.

The current implementation follows the methodology described in:

> Nioi M. et al.
> *Standardized Postmortem Pupillometry: Redefining Miosis, Mydriasis, and Their Biological Determinants.*
> (manuscript under peer review)

The software is intended to improve measurement reproducibility and facilitate the creation of standardized datasets for future multicenter validation studies.

---

## Intended Use

PupilLab is intended **exclusively for research purposes**.

It is **not** a medical device.

It is **not** intended for:

- clinical diagnosis;
- autonomous forensic conclusions;
- medico-legal decision making.

Measurements should always be independently verified by qualified investigators.

---

## Installation

Python 3.10 or newer is recommended.

Install the required packages:

```bash
pip install numpy pandas opencv-python Pillow scipy matplotlib openpyxl reportlab
```

Run the software:

```bash
python PupilLab.py
```

The splash screen image (`cover.png`) must be located in the same directory as the executable.

---

## Repository Structure

```
PupilLab/
│
├── PupilLab.py
├── cover.png
├── README.md
├── requirements.txt
├── LICENSE
└── output/
```

---

## Data Protection

Only anonymized or pseudonymized data should be analysed using PupilLab.

No identifiable information should be uploaded to the repository.

---

## Availability

The repository is currently maintained as a **private GitHub repository**.

Access may be provided to journal editors and peer reviewers for methodological evaluation during the peer-review process.

A public release is planned following scientific validation and publication.

---

## Future Development

Planned features include:

- SQLite database
- Advanced case management
- Structured toxicological database
- Quality-control module
- Repeatability analysis
- Observer agreement analysis
- Automated reporting
- Extended statistical framework
- Plugin architecture
- Public stable release (Version 1.0)

---

## Author

Department of Medical Sciences and Public Health

University of Cagliari

Italy

---

## Citation

If PupilLab contributes to your research, please cite the associated scientific publication describing the standardized postmortem pupillometry methodology once available.# PUPILLAB
Research software for standardized postmortem pupil-to-iris ratio (PIR) measurement and forensic pupillometry.
