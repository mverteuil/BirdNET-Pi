Of course. Here is the complete, finalized `README.md` file based on all of our
collaborative work.

-----

<h1 align="center">
    <img src="src/birdnetpi/web/static/images/birdnetpi-icon@0.25x.png" alt="BirdNET-Pi Logo" width="150" />
    <br />
    BirdNET-Pi
    </h1>
    <p align="center">
    <strong>The next generation of real-time, acoustic bird classification.</strong>
    <br />
    Modern, stable, and ready for the future.
</p>

## 🚀 About This Project

This project is a complete architectural rewrite of the
original [BirdNET-Pi](https://github.com/mcguirepr89/BirdNET-Pi). It honors the spirit of
the original while building a more robust, maintainable, and extensible platform for the
future of acoustic bird monitoring.

We've focused on key improvements to create a better experience for both users and
developers:

* **Modern Architecture**: We've moved from a collection of scripts to a modular Python
  framework. The result is a cleaner, more understandable, and highly customizable
  codebase.
* **Enhanced Performance & Stability**: By re-engineering the data flow and minimizing
  disk I/O, this version runs more efficiently and significantly reduces SD card wear—a
  common pain point for single-board computers.
* **Streamlined User Interface**: The web interface has been redesigned from the ground up
  for a more cohesive, intuitive, and user-friendly experience.
* **Developer-Friendly**: With modern tools and best practices, contributing to BirdNET-Pi
  has never been easier. We welcome you to help us build the future of this platform\!

### Why Python?

While languages like Go or Rust offer performance benefits, the core of BirdNET-Pi's
workload is the TensorFlow model itself. Switching languages would yield minimal gains.
Python's unparalleled ecosystem for data science, its gentle learning curve, and its
massive community make it the perfect choice for the long-term health and collaborative
spirit of this project.

-----

## ⚠️ License and Commercial Use

**This project is for non-commercial use only.** You may not use BirdNET-Pi, its
components, or any derivatives to create or sell a commercial product.

-----

## 🏁 Getting Started

During this pre-release phase, the simplest way to get up and running is with **Docker**.

1. **Build the Docker image:**
   ```bash
   docker-compose build
   ```
2. **Start the services:**
   ```bash
   docker-compose up -d
   ```

That's it! You can access the web interface at `http://<your-device-ip>:8000`.

A primary goal for our first official release is a simple, one-step installation script
for Raspberry Pi OS and other SBCs.

## 🖥️ Hardware

BirdNET-Pi is designed for flexibility. It runs beautifully on a variety of single-board
computers:

* Raspberry Pi 4B / 400 / 3B+
* Libre Computer "Le Potato"
* Libre Computer "Renegade"

Thanks to the new modular architecture, you can even run the recording, database, and
analysis services on separate machines for advanced, distributed setups.

## 🙏 Attributions and Acknowledgements

This project stands on the shoulders of giants. We are deeply grateful for the
foundational work of the following individuals and projects:

* **Patrick McGuire (@mcguirepr89)**: For the original vision and groundbreaking effort that started it all.
* **Stefan Kahl (@kahst)**: For the powerful **BirdNET** analysis framework that serves as the project's core.
* **Katsuya Hyodo (@PINTO0309)**: For the pre-compiled TFLite binaries that enable BirdNET to run on diverse hardware.
* **Ben Webber (@benwebber)**: For the elegant orphaned-commit asset distribution strategy.
* **Patrick Levin (@patlevin)**: For the comprehensive multilingual BirdNET label translations.
* **Frank Gill, David Donsker & Pamela Rasmussen (Eds)**: For the indispensable **IOC World Bird List**, which powers our species naming and translations.
* **Denis Lepage**: For **Avibase - the World Bird Database**, providing extensive multilingual bird names.

**IOC World Bird List Citation:**
Gill F, D Donsker & P Rasmussen (Eds). 2025. IOC World Bird List (v15.1). This list is provided under a [Creative Commons Attribution 3.0 Unported License](https://creativecommons.org/licenses/by/3.0/).

**Avibase Citation:**
Lepage, Denis. 2018. Avibase - the World Bird Database. Available at https://avibase.bsc-eoc.org/. Data used under [Creative Commons Attribution 4.0 International License](https://creativecommons.org/licenses/by/4.0/).

**BirdNET Label Translations:**
The multilingual label translations were originally compiled for the BirdNET-Pi project by Patrick Levin (@patlevin) and contributors, and are distributed under the same license as the BirdNET-Pi codebase.

## Open Source Dependencies

This project is built upon the hard work of many incredible open-source developers and
projects. We are immensely grateful for their contributions that make BirdNET-Pi possible.
The following is a list of the direct dependencies used in this project and their
respective licenses.

<details>
<summary><strong>Click to view the full list of dependencies</strong></summary>

```
Name                           Version            License
------------------------------ ------------------ --------------------------------------------------
APScheduler                    3.11.0             MIT License
Babel                          2.17.0             BSD License
GitPython                      3.1.44             BSD License
Jinja2                         3.1.6              BSD License
Markdown                       3.8.2              BSD 3-Clause License
MarkupSafe                     3.0.2              BSD License
PyYAML                         6.0.2              MIT License
Pygments                       2.19.2             BSD License
Pympler                        1.1                Apache Software License
SQLAlchemy                     2.0.41             MIT License
WTForms                        3.1.2              BSD License
Werkzeug                       3.1.3              BSD License
absl-py                        2.3.1              Apache Software License
altair                         4.2.2              BSD License
annotated-types                0.7.0              MIT License
anyio                          4.9.0              MIT License
apprise                        1.2.1              MIT License
ast-grep-cli                   0.39.2             MIT License
astral                         3.2                Apache Software License
astunparse                     1.6.3              BSD License
attrs                          25.3.0             MIT License
audioread                      3.0.1              MIT License
blinker                        1.9.0              MIT License
cachetools                     6.1.0              MIT License
certifi                        2025.7.9           Mozilla Public License 2.0 (MPL 2.0)
cffi                           1.17.1             MIT License
charset-normalizer             3.4.2              MIT License
click                          8.2.1              BSD 3-Clause License
colorama                       0.4.4              BSD License
contourpy                      1.3.2              BSD License
coverage                       7.9.2              Apache-2.0
cryptography                   45.0.6             Apache-2.0 OR BSD-3-Clause
cycler                         0.12.1             BSD License
decorator                      5.2.1              BSD License
dependency-injector            4.48.1             BSD License
entrypoints                    0.4                MIT License
et_xmlfile                     2.0.0              MIT License
exceptiongroup                 1.3.0              MIT License
fastapi                        0.116.1            MIT License
flatbuffers                    25.2.10            Apache Software License
fonttools                      4.58.5             MIT License
gast                           0.6.0              BSD License
gitdb                          4.0.12             BSD License
google-pasta                   0.2.0              Apache Software License
grpcio                         1.73.1             Apache Software License
h5py                           3.14.0             BSD-3-Clause License
h11                            0.16.0             MIT License
httpcore                       1.0.9              BSD License
httpx                          0.28.1             BSD License
idna                           3.10               BSD License
importlib_metadata             8.7.0              Apache Software License
iniconfig                      2.1.0              MIT License
joblib                         1.5.1              BSD License
jsonschema                     4.24.0             MIT License
jsonschema-specifications      2025.4.1           MIT License
keras                          3.10.0             Apache License 2.0
kiwisolver                     1.4.8              BSD License
lazy_loader                    0.4                BSD License
libclang                       18.1.1             Apache Software License
librosa                        0.11.0             ISC License (ISCL)
llvmlite                       0.44.0             BSD License
markdown-it-py                 3.0.0              MIT License
matplotlib                     3.10.3             PSF License
mdurl                          0.1.2              MIT License
ml_dtypes                      0.5.1              Apache Software License
msgpack                        1.1.1              Apache License 2.0
namex                          0.1.0              Apache License 2.0
narwhals                       1.46.0             MIT License
nodeenv                        1.9.1              BSD License
numba                          0.61.2             BSD License
numpy                          1.26.4             BSD License
oauthlib                       3.3.1              BSD-3-Clause
openpyxl                       3.1.5              MIT License
opt_einsum                     3.4.0              MIT License
optree                         0.16.0             Apache-2.0 License
packaging                      25.0               Apache Software License; BSD License
paho-mqtt                      2.1.0              EPL-2.0 OR BSD-3-Clause
pandas                         2.3.1              BSD License
pandas-stubs                   2.3.0.250703       BSD License
pillow                         11.3.0             MIT-CMU License
platformdirs                   4.3.8              MIT License
plotly                         6.2.0              MIT License
pluggy                         1.6.0              MIT License
pooch                          1.8.2              BSD License
protobuf                       3.20.3             BSD-3-Clause
psutil                         7.0.0              BSD License
py                             1.11.0             MIT License
pyarrow                        20.0.0             Apache Software License
pycparser                      2.22               BSD License
pydantic                       2.11.7             MIT License
pydantic_core                  2.33.2             MIT License
pydeck                         0.9.1              Apache License 2.0
pydub                          0.25.1             MIT License
pmemcache                      4.0.0             Apache License 2.0
pyleak                         0.1.14             Apache-2.0 License
pyparsing                      3.2.3              MIT License
pyright                        1.1.403            MIT License
pytest                         7.1.2              MIT License
pytest-asyncio                 0.23.8             Apache Software License
pytest-cov                     6.2.1              MIT License
pytest-mock                    3.7.0              MIT License
python-dateutil                2.9.0.post0        Apache Software License; BSD License
python-multipart               0.0.20             Apache Software License
pytz                           2025.2             MIT License
referencing                    0.36.2             MIT License
requests                       2.32.4             Apache Software License
requests-oauthlib              2.0.0              BSD License
rich                           14.0.0             MIT License
rpds-py                        0.26.0             MIT License
ruff                           0.12.5             MIT License
scikit-learn                   1.7.0              BSD License
scipy                          1.16.0             BSD License
seaborn                        0.13.2             BSD License
semver                         3.0.4              BSD License
six                            1.17.0             MIT License
smmap                          5.0.2              BSD License
sniffio                        1.3.1              Apache Software License; MIT License
sounddevice                    0.5.2              MIT License
soundfile                      0.13.1             BSD License
soxr                           0.5.0.post1        LGPLv2+
sqladmin                       0.21.0             BSD License
starlette                      0.47.1             BSD License
streamlit                      1.19.0             Apache Software License
structlog                      25.4.0             Apache Software License; MIT License
suntime                        1.3.2              LGPLv3
tensorboard                    2.19.0             Apache Software License
tensorboard-data-server        0.7.2              Apache Software License
tensorflow                     2.19.0             Apache Software License
tensorflow-io-gcs-filesystem   0.37.1             Apache Software License
termcolor                      3.1.0              MIT License
threadpoolctl                  3.6.0              BSD License
toml                           0.10.2             MIT License
toolz                          1.0.0              BSD License
tornado                        6.5.1              Apache Software License
tqdm                           4.67.1             MIT License; MPL 2.0
types-Pillow                   10.2.0.20240822    Apache Software License
types-SQLAlchemy               1.4.53.38          Apache Software License
types-decorator                5.2.0.20250324     Apache Software License
types-paho-mqtt                1.6.0.20240321     Apache Software License
types-psutil                   7.0.0.20250801     Apache-2.0 License
types-pytz                     2025.2.0.20250516  Apache-2.0 License
types-requests                 2.32.4.20250611    Apache-2.0 License
types-setuptools               80.9.0.20250801    Apache-2.0 License
types-tqdm                     4.67.0.20250516    Apache-2.0 License
types-tzlocal                  5.1.0.1            Apache Software License
types-urllib3                  1.26.25.14         Apache Software License
typing-inspection              0.4.1              MIT License
typing_extensions              4.14.1             PSF License v2
tzdata                         2025.2             Apache Software License
tzlocal                        5.3.1              MIT License
urllib3                        2.5.0              MIT License
uvicorn                        0.35.0             BSD License
validators                     0.35.0             MIT License
websockets                     15.0.1             BSD License
wrapt                          1.17.2             BSD License
zipp                           3.23.0             MIT License
```

</details>

<br/>

## 🖼️ Screenshots

(Coming Soon)
