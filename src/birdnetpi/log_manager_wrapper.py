from .managers.log_manager import LogManager

if __name__ == "__main__":
    log_manager = LogManager()
    logs = log_manager.get_logs()
    print(logs)
