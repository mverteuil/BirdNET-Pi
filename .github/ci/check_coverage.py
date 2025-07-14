import sys
import xml.etree.ElementTree as ET

COVERAGE_THRESHOLD = 80.0
COVERAGE_FILE = "coverage.xml"  # Relative to the working-directory of the step

try:
    tree = ET.parse(COVERAGE_FILE)
    root = tree.getroot()
    coverage_element = root.find("coverage")
    if coverage_element is not None:
        line_rate = float(coverage_element.attrib.get("line-rate", 0))
        coverage_percentage = line_rate * 100
        print(f"Current code coverage: {coverage_percentage:.2f}%")

        if coverage_percentage < COVERAGE_THRESHOLD:
            print(
                f"Error: Code coverage ({coverage_percentage:.2f}%) is below the "
                f"required threshold of {COVERAGE_THRESHOLD}%"
            )
            sys.exit(1)
        else:
            print(
                f"Code coverage ({coverage_percentage:.2f}%) meets or exceeds the "
                f"required threshold of {COVERAGE_THRESHOLD}%"
            )
    else:
        print(f"Error: 'coverage' element not found in {COVERAGE_FILE}.")
        sys.exit(1)

except FileNotFoundError:
    print(
        f"Error: Coverage report file not found at {COVERAGE_FILE}. "
        "Make sure pytest --cov generated it."
    )
    sys.exit(1)
except Exception as e:
    print(f"An error occurred while parsing the coverage report: {e}")
    sys.exit(1)
