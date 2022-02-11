#!/usr/bin/env bash
# This installs the services that have been selected
set -x # Uncomment to enable debugging
trap 'rm -f ${tmpfile}' EXIT
trap 'exit 1' SIGINT SIGHUP
USER=pi
HOME=/home/pi
my_dir=${HOME}/BirdNET-Pi/scripts
tmpfile=$(mktemp)
nomachine_url="https://download.nomachine.com/download/7.7/Arm/nomachine_7.7.4_1_arm64.deb"
gotty_url="https://github.com/yudai/gotty/releases/download/v1.0.1/gotty_linux_arm.tar.gz"
config_file="$(dirname ${my_dir})/birdnet.conf"

set_hostname() {
  if [ "$(hostname)" == "raspberrypi" ];then
    echo "Setting hostname to 'birdnetpi'"
    hostnamectl set-hostname birdnetpi
    sed -i 's/raspberrypi/birdnetpi/g' /etc/hosts
  fi
}

install_ftpd() {
  if ! [ -f /etc/ftpuseres ];then
    apt -y install ftpd
  fi
}

update_system() {
  apt update && apt -y upgrade
}

install_scripts() {
  echo "Installing BirdNET-Pi scripts to /usr/local/bin"
  ln -sf ${my_dir}/* /usr/local/bin/
  rm /usr/local/bin/index.html
}

install_mariadb() {
  if ! which mysql &> /dev/null;then
    echo "Installing MariaDB Server"
    apt -qqy update
    apt -qqy install mariadb-server
    echo "MariaDB Installed"
  fi
  echo "Initializing the database"
  source /etc/os-release
  if [[ "${VERSION_CODENAME}" == "buster" ]];then
    USER=${USER} ${my_dir}/createdb_buster.sh
  elif [[ "${VERSION_CODENAME}" == "bullseye" ]];then
    USER=${USER} ${my_dir}/createdb_bullseye.sh
  fi
  systemctl restart php${php_version}-fpm
}

install_birdnet_analysis() {
  echo "Installing the birdnet_analysis.service"
  cat << EOF > /etc/systemd/system/birdnet_analysis.service
[Unit]
Description=BirdNET Analysis
After=birdnet_server.service
Requires=birdnet_server.service
[Service]
Restart=always
Type=simple
RestartSec=2
User=${USER}
ExecStart=/usr/local/bin/birdnet_analysis.sh
[Install]
WantedBy=multi-user.target
EOF
  systemctl enable birdnet_analysis.service
}

install_birdnet_server() {
  echo "Installing the birdnet_server.service"
  cat << EOF > /etc/systemd/system/birdnet_server.service
[Unit]
Description=BirdNET Analysis Server
Before=birdnet_analysis.service
[Service]
Restart=always
Type=simple
RestartSec=10
User=${USER}
ExecStart=/usr/local/bin/server.py
[Install]
WantedBy=multi-user.target
EOF
  systemctl enable birdnet_server.service
}

install_extraction_service() {
  echo "Installing the extraction.service and extraction.timer"
  cat << EOF > /etc/systemd/system/extraction.service
[Unit]
Description=BirdNET BirdSound Extraction
[Service]
Restart=on-failure
RestartSec=3
Type=simple
User=${USER}
ExecStart=/usr/local/bin/extract_new_birdsounds.sh
[Install]
WantedBy=multi-user.target
EOF
  cat << EOF > /etc/systemd/system/extraction.timer
[Unit]
Description=BirdNET BirdSound Extraction Timer
Requires=extraction.service
[Timer]
Unit=extraction.service
OnCalendar=*:*:0/10
[Install]
WantedBy=multi-user.target
EOF
  systemctl enable extraction.timer
  systemctl enable extraction.service
}

install_pushed_notifications() {
  echo "Installing Pushed.co mobile notifications"
  cat << EOF > /etc/systemd/system/pushed_notifications.service
[Unit]
Description=BirdNET-Pi Pushed.co Notifications
[Service]
Restart=on-success
RestartSec=3
Type=simple
User=pi
ExecStart=/usr/local/bin/species_notifier.sh
[Install]
WantedBy=multi-user.target
EOF
  systemctl enable pushed_notifications.service
}

create_necessary_dirs() {
  echo "Creating necessary directories"
  [ -d ${EXTRACTED} ] || sudo -u ${USER} mkdir -p ${EXTRACTED}
  [ -d ${EXTRACTED}/By_Date ] || sudo -u ${USER} mkdir -p ${EXTRACTED}/By_Date
  [ -d ${EXTRACTED}/By_Common_Name ] || sudo -u ${USER} mkdir -p ${EXTRACTED}/By_Common_Name
  [ -d ${EXTRACTED}/By_Scientific_Name ] || sudo -u ${USER} mkdir -p ${EXTRACTED}/By_Scientific_Name
  [ -d ${EXTRACTED}/Charts ] || sudo -u ${USER} mkdir -p ${EXTRACTED}/Charts
  [ -d ${PROCESSED} ] || sudo -u ${USER} mkdir -p ${PROCESSED}

  sudo -u ${USER} ln -fs $(dirname ${my_dir})/homepage/* ${EXTRACTED}  
  if [ ! -z ${BIRDNETLOG_URL} ];then
    BIRDNETLOG_URL="$(echo ${BIRDNETLOG_URL} | sed 's/\/\//\\\/\\\//g')"
    sudo -u${USER} sed -i "s/http:\/\/birdnetpi.local:8080/${BIRDNETLOG_URL}/g" $(dirname ${my_dir})/homepage/*.html
    sudo -u${USER} sed -i "s/http:\/\/birdnetpi.local:8080/${BIRDNETLOG_URL}/g" $(dirname ${my_dir})/scripts/*.html
    sudo -u${USER} sed -i "s/http:\/\/birdnetpi.local:8080/${BIRDNETLOG_URL}/g" $(dirname ${my_dir})/scripts/*.html
    sudo -u${USER} sed -i "s/http:\/\/birdnetpi.local:8080/${BIRDNETLOG_URL}/g" $(dirname ${my_dir})/scripts/*.php
    sudo -u${USER} sed -i "s/http:\/\/birdnetpi.local:8080/${BIRDNETLOG_URL}/g" $(dirname ${my_dir})/scripts/*/*.php
  fi
  if [ ! -z ${WEBTERMINAL_URL} ];then
    WEBTERMINAL_URL="$(echo ${WEBTERMINAL_URL} | sed 's/\/\//\\\/\\\//g')"
    sudo -u${USER} sed -i "s/http:\/\/birdnetpi.local:8888/${WEBTERMINAL_URL}/g" $(dirname ${my_dir})/homepage/*.html
    sudo -u${USER} sed -i "s/http:\/\/birdnetpi.local:8888/${WEBTERMINAL_URL}/g" $(dirname ${my_dir})/scripts/*.html
    sudo -u${USER} sed -i "s/http:\/\/birdnetpi.local:8888/${WEBTERMINAL_URL}/g" $(dirname ${my_dir})/scripts/*.html
    sudo -u${USER} sed -i "s/http:\/\/birdnetpi.local:8888/${WEBTERMINAL_URL}/g" $(dirname ${my_dir})/scripts/*.php
    sudo -u${USER} sed -i "s/http:\/\/birdnetpi.local:8888/${WEBTERMINAL_URL}/g" $(dirname ${my_dir})/scripts/*/*.php

  fi

  sudo -u ${USER} ln -fs $(dirname ${my_dir})/model/labels.txt ${my_dir}/
  sudo -u ${USER} ln -fs $(dirname ${my_dir})/scripts ${EXTRACTED}
  if [ -z ${BIRDNETPI_URL} ];then
    sudo -u${USER} sed -i "s/birdnetpi.local/$(hostname).local/g" $(dirname ${my_dir})/homepage/*.html
    sudo -u${USER} sed -i "s/birdnetpi.local/$(hostname).local/g" $(dirname ${my_dir})/scripts/*.html
    sudo -u${USER} sed -i "s/birdnetpi.local/$(hostname).local/g" $(dirname ${my_dir})/scripts/*.html
    sudo -u${USER} sed -i "s/birdnetpi.local/$(hostname).local/g" $(dirname ${my_dir})/scripts/*.php
    sudo -u${USER} sed -i "s/birdnetpi.local/$(hostname).local/g" $(dirname ${my_dir})/scripts/*/*.php
  else
    BIRDNETPI_URL="$(echo ${BIRDNETPI_URL} | sed 's/\/\//\\\/\\\//g')"
    sudo -u${USER} sed -i "s/http:\/\/birdnetpi.local/${BIRDNETPI_URL}/g" $(dirname ${my_dir})/homepage/*.html
    sudo -u${USER} sed -i "s/http:\/\/birdnetpi.local/${BIRDNETPI_URL}/g" $(dirname ${my_dir})/scripts/*.html
    sudo -u${USER} sed -i "s/http:\/\/birdnetpi.local/${BIRDNETPI_URL}/g" $(dirname ${my_dir})/scripts/*.html
    sudo -u${USER} sed -i "s/http:\/\/birdnetpi.local/${BIRDNETPI_URL}/g" $(dirname ${my_dir})/scripts/*.php
    sudo -u${USER} sed -i "s/http:\/\/birdnetpi.local/${BIRDNETPI_URL}/g" $(dirname ${my_dir})/scripts/*/*.php
  fi

  sudo -u ${USER} ln -fs $(dirname ${my_dir})/scripts/spectrogram.php ${EXTRACTED}
  sudo -u ${USER} ln -fs $(dirname ${my_dir})/scripts/viewday.php ${EXTRACTED}
  sudo -u ${USER} ln -fs $(dirname ${my_dir})/scripts/overview.php ${EXTRACTED}
  sudo -u ${USER} ln -fs $(dirname ${my_dir})/scripts/viewdb.php ${EXTRACTED}
  sudo -u ${USER} ln -fs $(dirname ${my_dir})/homepage/images/favicon.ico ${EXTRACTED}
  sudo -u ${USER} ln -fs ${HOME}/phpsysinfo ${EXTRACTED}
  sudo -u ${USER} cp -f $(dirname ${my_dir})/templates/phpsysinfo.ini ${HOME}/phpsysinfo/
  sudo -u ${USER} cp -f $(dirname ${my_dir})/templates/green_bootstrap.css ${HOME}/phpsysinfo/templates/
  sudo -u ${USER} cp -f $(dirname ${my_dir})/templates/index_bootstrap.html ${HOME}/phpsysinfo/templates/html

  echo "Setting Wttr.in URL to "${LATITUDE}", "${LONGITUDE}""
  sudo -u${USER} sed -i "s/https:\/\/v2.wttr.in\//https:\/\/v2.wttr.in\/"${LATITUDE},${LONGITUDE}"/g" $(dirname ${my_dir})/homepage/menu.html
  chmod -R g+rw $(dirname ${my_dir})
  chmod -R g+rw ${RECS_DIR}
}

generate_BirdDB() {
  echo "Generating BirdDB.txt"
  if ! [ -f $(dirname ${my_dir})/BirdDB.txt ];then
    sudo -u ${USER} touch $(dirname ${my_dir})/BirdDB.txt
    echo "Date;Time;Sci_Name;Com_Name;Confidence;Lat;Lon;Cutoff;Week;Sens;Overlap" | sudo -u ${USER} tee -a $(dirname ${my_dir})/BirdDB.txt
  elif ! grep Date $(dirname ${my_dir})/BirdDB.txt;then
    sudo -u ${USER} sed -i '1 i\Date;Time;Sci_Name;Com_Name;Confidence;Lat;Lon;Cutoff;Week;Sens;Overlap' $(dirname ${my_dir})/BirdDB.txt
  fi
  ln -sf $(dirname ${my_dir})/BirdDB.txt ${my_dir}/BirdDB.txt &&
	  chown pi:pi ${my_dir}/BirdDB.txt && chmod g+rw ${my_dir}/BirdDB.txt
}

install_alsa() {
  echo "Checking for alsa-utils and pulseaudio"
  if which arecord &> /dev/null ;then
    echo "alsa-utils installed"
  else
    echo "Installing alsa-utils"
    apt -qqq update 
    apt install -qqy alsa-utils
    echo "alsa-utils installed"
  fi
  if which pulseaudio &> /dev/null;then
    echo "PulseAudio installed"
  else
    echo "Installing pulseaudio"
    apt -qqq update
    apt install -qqy pulseaudio
    echo "PulseAudio installed"
  fi
  if ! [ -d /etc/lightdm ];then
    systemctl set-default multi-user.target
    ln -fs /lib/systemd/system/getty@.service /etc/systemd/system/getty.target.wants/getty@tty1.service
    cat > /etc/systemd/system/getty@tty1.service.d/autologin.conf << EOF
[Service]
ExecStart=
ExecStart=-/sbin/agetty --autologin $USER --noclear %I \$TERM
EOF
  fi
}

install_recording_service() {
  echo "Installing birdnet_recording.service"
  cat << EOF > /etc/systemd/system/birdnet_recording.service
[Unit]
Description=BirdNET Recording
[Service]
Environment=XDG_RUNTIME_DIR=/run/user/1000
Restart=always
Type=simple
RestartSec=3
User=${USER}
ExecStart=/usr/local/bin/birdnet_recording.sh
[Install]
WantedBy=multi-user.target
EOF
  systemctl enable birdnet_recording.service
}

install_caddy() {
  if ! which caddy &> /dev/null ;then
    echo "Installing Caddy"
    curl -1sLf \
      'https://dl.cloudsmith.io/public/caddy/stable/setup.deb.sh' \
        | sudo -E bash
    apt -qq update
    apt install -qqy caddy=2.4.5 && apt-mark hold caddy
    systemctl enable --now caddy
    usermod -aG pi caddy
  else
    echo "Caddy is installed"
    systemctl enable --now caddy
    usermod -aG pi caddy
  fi
}

install_Caddyfile() {
  echo "Installing the Caddyfile"
  [ -d /etc/caddy ] || mkdir /etc/caddy
  if [ -f /etc/caddy/Caddyfile ];then
    cp /etc/caddy/Caddyfile{,.original}
  fi
  php_version="$(awk -F'php' '{print $3}' <(ls -l $(which /etc/alternatives/php)))"
  if ! [ -z ${CADDY_PWD} ];then
  HASHWORD=$(caddy hash-password -plaintext ${CADDY_PWD})
  cat << EOF > /etc/caddy/Caddyfile
http://localhost http://$(hostname).local ${BIRDNETPI_URL} {
  root * ${EXTRACTED}
  file_server browse
  basicauth /Processed* {
    birdnet ${HASHWORD}
  }
  basicauth /scripts* {
    birdnet ${HASHWORD}
  }
  basicauth /stream {
    birdnet ${HASHWORD}
  }
  basicauth /phpsysinfo* {
    birdnet ${HASHWORD}
  }
  reverse_proxy /stream localhost:8000
  php_fastcgi unix//run/php/php${php_version}-fpm.sock
}
EOF
  else
    cat << EOF > /etc/caddy/Caddyfile
http://localhost http://$(hostname).local ${BIRDNETPI_URL} {
  root * ${EXTRACTED}
  file_server browse
  reverse_proxy /stream localhost:8000
  php_fastcgi unix//run/php/php${php_version}-fpm.sock
}
EOF
  fi

  if [ ! -z ${WEBTERMINAL_URL} ] && [ ! -z ${HASHWORD} ];then
    cat << EOF >> /etc/caddy/Caddyfile
${WEBTERMINAL_URL} {
  basicauth {
    birdnet ${HASHWORD}
  }
  reverse_proxy localhost:8888
}
EOF
  elif [ ! -z ${WEBTERMINAL_URL} ] && [ -z ${HASHWORD} ];then
    cat << EOF >> /etc/caddy/Caddyfile
${WEBTERMINAL_URL} {
  reverse_proxy localhost:8888
}
EOF
  fi

  if [ ! -z ${BIRDNETLOG_URL} ];then
    cat << EOF >> /etc/caddy/Caddyfile
${BIRDNETLOG_URL} {
  reverse_proxy localhost:8080
}
EOF
  fi
  systemctl reload caddy
}

update_etc_hosts() {
  sed -ie s/'$(hostname).local'/"$(hostname).local ${BIRDNETPI_URL//https:\/\/} ${WEBTERMINAL_URL//https:\/\/} ${BIRDNETLOG_URL//https:\/\/}"/g /etc/hosts
}

install_avahi_aliases() {
  echo "Installing Avahi Services"
  if ! which avahi-publish &> /dev/null; then
    echo "Installing avahi-utils"
    apt install -y avahi-utils &> /dev/null
  fi
  echo "Installing avahi-alias service"
  cat << 'EOF' > /etc/systemd/system/avahi-alias@.service
[Unit]
Description=Publish %I as alias for %H.local via mdns
After=network.target network-online.target
Requires=network-online.target
[Service]
Restart=always
RestartSec=3
Type=simple
ExecStart=/bin/bash -c "/usr/bin/avahi-publish -a -R %I $(hostname -I |cut -d' ' -f1)"
[Install]
WantedBy=multi-user.target
EOF
systemctl enable avahi-alias@"$(hostname)".local.service
}

install_spectrogram_service() {
  cat << EOF > /etc/systemd/system/spectrogram_viewer.service
[Unit]
Description=BirdNET-Pi Spectrogram Viewer
[Service]
Restart=always
RestartSec=10
Type=simple
User=${USER}
ExecStart=/usr/local/bin/spectrogram.sh
[Install]
WantedBy=multi-user.target
EOF
   systemctl enable spectrogram_viewer.service
}

install_chart_viewer_service() {
  echo "Installing the chart_viewer.service"
  cat << EOF > /etc/systemd/system/chart_viewer.service
[Unit]
Description=BirdNET-Pi Chart Viewer Service
[Service]
Restart=always
RestartSec=300
Type=simple
User=pi
ExecStart=/usr/local/bin/daily_plot.py
[Install]
WantedBy=multi-user.target
EOF
  systemctl enable chart_viewer.service
}

install_gotty_logs() {
  echo "Installing GoTTY logging"
  if ! which gotty &> /dev/null;then
    echo "Installing GoTTY binary"
    wget -c ${gotty_url} -O - |  tar -xz -C /usr/local/bin/
  fi
  sudo -u ${USER} ln -sf $(dirname ${my_dir})/templates/gotty \
    ${HOME}/.gotty
  sudo -u ${USER} ln -sf $(dirname ${my_dir})/templates/bashrc \
    ${HOME}/.bashrc
  echo "Installing the birdnet_log.service"
  cat << EOF > /etc/systemd/system/birdnet_log.service
[Unit]
Description=BirdNET Analysis Log
[Service]
Restart=on-failure
RestartSec=3
Type=simple
User=${USER}
Environment=TERM=xterm-256color
ExecStart=/usr/local/bin/gotty -p 8080 --title-format "BirdNET-Pi Log" journalctl --no-hostname -o short -fu birdnet_server.service -u birdnet_analysis.service
[Install]
WantedBy=multi-user.target
EOF
  systemctl enable birdnet_log.service
  echo "Installing the web_terminal.service"
  cat << EOF > /etc/systemd/system/web_terminal.service
[Unit]
Description=BirdNET-Pi Web Terminal
[Service]
Restart=on-failure
RestartSec=3
Type=simple
User=${USER}
Environment=TERM=xterm-256color
ExecStart=/usr/local/bin/gotty -w -p 8888 --title-format "BirdNET-Pi Terminal" bash
[Install]
WantedBy=multi-user.target
EOF
  systemctl enable web_terminal.service
}

install_sox() {
  if which sox &> /dev/null;then
    echo "Sox is installed"
  else
    echo "Installing sox"
    apt -qq update
    apt install -y sox
    echo "Sox installed"
  fi
}

install_php() {
  if ! which php &> /dev/null || ! which php-fpm || ! apt list --installed | grep php-xml;then
    echo "Installing PHP modules"
    apt -qq update
    apt install -qqy php php-fpm php-mysql php-xml php-zip
  else
    echo "PHP and PHP-FPM installed"
  fi
    echo "Configuring PHP for Caddy"
    sed -i 's/www-data/caddy/g' /etc/php/*/fpm/pool.d/www.conf
    systemctl restart php7\*-fpm.service
    echo "Adding Caddy sudoers rule"
    cat << EOF > /etc/sudoers.d/010_caddy-nopasswd
caddy ALL=(ALL) NOPASSWD: ALL
EOF
    chmod 0440 /etc/sudoers.d/010_caddy-nopasswd
  if [ ! -d ${HOME}/phpsysinfo ];then
    echo "Fetching phpSysInfo"
    sudo -u ${USER} git clone https://github.com/phpsysinfo/phpsysinfo.git \
      ${HOME}/phpsysinfo
  fi 
}

install_icecast() {
  if ! which icecast2;then
    echo "Installing IceCast2"
    apt -qq update
    echo "icecast2 icecast2/icecast-setup boolean false" | debconf-set-selections
    apt install -qqy icecast2 
    config_icecast
    systemctl enable icecast2.service
    /etc/init.d/icecast2 start
  else
    echo "Icecast2 is installed"
    config_icecast
    systemctl enable icecast2.service
    /etc/init.d/icecast2 start
  fi
}

config_icecast() {
  if [ -f /etc/icecast2/icecast.xml ];then 
    cp /etc/icecast2/icecast.xml{,.prebirdnetpi}
  fi
  sed -i 's/>admin</>birdnet</g' /etc/icecast2/icecast.xml
  passwords=("source-" "relay-" "admin-" "master-" "")
  for i in "${passwords[@]}";do
  sed -i "s/<${i}password>.*<\/${i}password>/<${i}password>${ICE_PWD}<\/${i}password>/g" /etc/icecast2/icecast.xml
  done
}

install_livestream_service() {
  echo "Installing Live Stream service"
  cat << EOF > /etc/systemd/system/livestream.service
[Unit]
Description=BirdNET-Pi Live Stream
After=network-online.target
Requires=network-online.target
[Service]
Environment=XDG_RUNTIME_DIR=/run/user/1000
Restart=always
Type=simple
RestartSec=3
User=${USER}
ExecStart=/usr/local/bin/livestream.sh
[Install]
WantedBy=multi-user.target
EOF
  systemctl enable livestream.service
}

install_nomachine() {
  if [ ! -d /usr/share/NX ] && [ -d /etc/lightdm ];then
    echo "Installing NoMachine"
    curl -s -o ${HOME}/nomachine.deb -O "${nomachine_url}"
    apt install -y ${HOME}/nomachine.deb
    rm -f ${HOME}/nomachine.deb
    echo "Enabling VNC"
    systemctl enable --now vncserver-x11-serviced.service
  fi
}

install_cleanup_cron() {
  echo "Installing the cleanup.cron"
  cat $(dirname ${my_dir})/templates/cleanup.cron >> /etc/crontab
}

install_selected_services() {
  set_hostname
  update_system
  install_scripts
  install_birdnet_analysis
  install_birdnet_server

  if [[ "${DO_EXTRACTIONS}" =~ [Yy] ]];then
    install_extraction_service
  fi

  if [[ "${DO_RECORDING}" =~ [Yy] ]];then
    install_alsa
    install_recording_service
  fi

    install_php
    install_caddy
    install_Caddyfile
    update_etc_hosts
    install_avahi_aliases
    install_gotty_logs
    install_sox
    install_mariadb
    install_spectrogram_service
    install_chart_viewer_service
    install_pushed_notifications

  if [ ! -z "${ICE_PWD}" ];then
    install_icecast
    install_livestream_service
  fi

  if [[ "${INSTALL_NOMACHINE}" =~ [Yy] ]];then
    install_nomachine
  fi

  create_necessary_dirs
  generate_BirdDB
  install_cleanup_cron
  install_ftpd
}

if [ -f ${config_file} ];then 
  source ${config_file}
  install_selected_services
else
  echo "Unable to find a configuration file. Please make sure that $config_file exists."
fi
