import os
import sys

# Add the src directory to the Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from managers.log_manager import LogManager

if __name__ == "__main__":
    log_manager = LogManager()
    logs = log_manager.get_logs()
    print(logs)
