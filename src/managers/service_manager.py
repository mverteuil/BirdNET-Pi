import subprocess


class ServiceManager:
    def restart_service(self, service_name: str):
        try:
            subprocess.run(["sudo", "systemctl", "restart", service_name], check=True)
            print(f"Service {service_name} restarted successfully.")
        except subprocess.CalledProcessError as e:
            print(f"Error restarting service {service_name}: {e}")
        except FileNotFoundError:
            print("Error: systemctl command not found. Is systemd installed?")

    def stop_service(self, service_name: str):
        try:
            subprocess.run(["sudo", "systemctl", "stop", service_name], check=True)
            print(f"Service {service_name} stopped successfully.")
        except subprocess.CalledProcessError as e:
            print(f"Error stopping service {service_name}: {e}")
        except FileNotFoundError:
            print("Error: systemctl command not found. Is systemd installed?")

    def start_service(self, service_name: str):
        try:
            subprocess.run(["sudo", "systemctl", "start", service_name], check=True)
            print(f"Service {service_name} started successfully.")
        except subprocess.CalledProcessError as e:
            print(f"Error starting service {service_name}: {e}")
        except FileNotFoundError:
            print("Error: systemctl command not found. Is systemd installed?")

    def restart_services(self, services: list[str]):
        for service in services:
            self.restart_service(service)
