#!/usr/bin/env bash
# This installs the services that have been selected
#set -x # Uncomment to enable debugging
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
  if [ "$(hostname)" != "birdnetpi" ];then
    echo "Setting hostname to 'birdnetpi'"
    hostnamectl set-hostname birdnetpi
    sed -i 's/raspberrypi/birdnetpi/g' /etc/hosts
    sed -i 's/localhost$/localhost birdnetpi.local/g' /etc/hosts
  fi
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
  ${my_dir}/createdb.sh
}

install_birdnet_analysis() {
  echo "Installing the birdnet_analysis.service"
  cat << EOF > /etc/systemd/system/birdnet_analysis.service
[Unit]
Description=BirdNET Analysis
[Service]
Restart=always
RuntimeMaxSec=10800
Type=simple
RestartSec=2
User=${USER}
ExecStart=/usr/local/bin/birdnet_analysis.sh
[Install]
WantedBy=multi-user.target
EOF
  systemctl enable birdnet_analysis.service
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
  [ -d ${PROCESSED} ] || sudo -u ${USER} mkdir -p ${PROCESSED}

  sudo -u ${USER} ln -fs $(dirname ${my_dir})/homepage/* ${EXTRACTED}  
  if [ ! -z ${BIRDNETLOG_URL} ];then
    BIRDNETLOG_URL="$(echo ${BIRDNETLOG_URL} | sed 's/\/\//\\\/\\\//g')"
    sudo -u${USER} sed -i "s/http:\/\/birdnetpi.local:8080/"${BIRDNETLOG_URL}"/g" $(dirname ${my_dir})/homepage/*.html
    phpfiles="$(grep -l "birdnetpi.local:8080" ${my_dir}/*.php)"
    for i in "${phpfiles[@]}";do
      sudo -u${USER} sed -i "s/http:\/\/birdnetpi.local:8080/"${BIRDNETLOG_URL}"/g" ${i}
    done
  fi
  if [ ! -z ${EXTRACTIONLOG_URL} ];then
    EXTRACTIONLOG_URL="$(echo ${EXTRACTIONLOG_URL} | sed 's/\/\//\\\/\\\//g')"
    sudo -u${USER} sed -i "s/http:\/\/birdnetpi.local:8888/"${EXTRACTIONLOG_URL}"/g" $(dirname ${my_dir})/homepage/*.html
    phpfiles="$(grep -l "birdnetpi.local:8888" ${my_dir}/*.php)"
    for i in "${phpfiles[@]}";do
      sudo -u${USER} sed -i "s/http:\/\/birdnetpi.local:8888/"${EXTRACTIONLOG_URL}"/g" ${i}
    done
  fi

  sudo -u ${USER} ln -fs $(dirname ${my_dir})/scripts ${EXTRACTED}
  if [ ! -z ${BIRDNETPI_URL} ];then
    BIRDNETPI_URL="$(echo ${BIRDNETPI_URL} | sed 's/\/\//\\\/\\\//g')"
    sudo -u${USER} sed -i "s/http:\/\/birdnetpi.local/"${BIRDNETPI_URL}"/g" $(dirname ${my_dir})/homepage/*.html
    phpfiles="$(grep -l birdnetpi.local ${my_dir}/*.php)"
    for i in "${phpfiles[@]}";do
      sudo -u${USER} sed -i "s/http:\/\/birdnetpi.local/"${BIRDNETPI_URL}"/g" ${i}
    done
  fi

  sudo -u ${USER} ln -fs $(dirname ${my_dir})/scripts/spectrogram.php ${EXTRACTED}
  sudo -u ${USER} ln -fs $(dirname ${my_dir})/scripts/viewdb.php ${EXTRACTED}
  sudo -u ${USER} ln -fs ${HOME}/phpsysinfo ${EXTRACTED}
  sudo -u ${USER} cp -f $(dirname ${my_dir})/templates/phpsysinfo.ini ${HOME}/phpsysinfo/
  sudo -u ${USER} cp -f $(dirname ${my_dir})/templates/green_bootstrap.css ${HOME}/phpsysinfo/templates/
  sudo -u ${USER} cp -f $(dirname ${my_dir})/templates/index_bootstrap.html ${HOME}/phpsysinfo/templates/html


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
    apt install -qqy caddy
    systemctl enable --now caddy
  else
    echo "Caddy is installed"
    systemctl enable --now caddy
  fi
}

install_Caddyfile() {
  echo "Installing the Caddyfile"
  [ -d /etc/caddy ] || mkdir /etc/caddy
  if [ -f /etc/caddy/Caddyfile ];then
    cp /etc/caddy/Caddyfile{,.original}
  fi
  HASHWORD=$(caddy hash-password -plaintext ${CADDY_PWD})
  cat << EOF > /etc/caddy/Caddyfile
http://localhost http://birdnetpi.local ${BIRDNETPI_URL} {
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
  php_fastcgi unix//run/php/php7.3-fpm.sock
}
EOF
  if [ ! -z ${EXTRACTIONLOG_URL} ];then
    cat << EOF >> /etc/caddy/Caddyfile

${EXTRACTIONLOG_URL} {
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
  #BIRDNETPI_URL="$(echo ${BIRDNETPI_URL} | sed 's/\/\//\\\/\\\//g')"
  #EXTRACTIONLOG_URL="$(echo ${EXTRACTIONLOG_URL} | sed 's/\/\//\\\/\\\//g')"
  #BIRDNETLOG_URL="$(echo ${BIRDNETLOG_URL} | sed 's/\/\//\\\/\\\//g')"
  sed -ie s/'birdnetpi.local'/"birdnetpi.local ${BIRDNETPI_URL//https:\/\/} ${EXTRACTIONLOG_URL//https:\/\/} ${BIRDNETLOG_URL//https:\/\/}"/g /etc/hosts
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
Type=simple
ExecStart=/bin/bash -c "/usr/bin/avahi-publish -a -R %I $(avahi-resolve -4 -n %H.local | cut -f 2)"

[Install]
WantedBy=multi-user.target
EOF
  systemctl enable avahi-alias@birdnetpi.local.service
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

install_gotty_logs() {
  echo "Installing GoTTY logging"
  if ! which gotty &> /dev/null;then
    echo "Installing GoTTY binary"
    wget -c ${gotty_url} -O - |  tar -xz -C /usr/local/bin/
  fi
  sudo -u ${USER} ln -sf $(dirname ${my_dir})/templates/gotty \
    ${HOME}/.gotty
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
ExecStart=/usr/local/bin/gotty -p 8080 --title-format "BirdNET-Pi Log" journalctl -o cat -fu birdnet_analysis.service

[Install]
WantedBy=multi-user.target
EOF
  systemctl enable birdnet_log.service
  echo "Installing the extraction_log.service"
  cat << EOF > /etc/systemd/system/extraction_log.service
[Unit]
Description=BirdNET Extraction Log

[Service]
Restart=on-failure
RestartSec=3
Type=simple
User=${USER}
Environment=TERM=xterm-256color
ExecStart=/usr/local/bin/gotty -p 8888 --title-format "Extractions Log" journalctl -o cat -fu extraction.service

[Install]
WantedBy=multi-user.target
EOF
  systemctl enable extraction_log.service
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
  if ! which php &> /dev/null || ! which php-fpm7.3 || ! apt list --installed | grep php-xml;then
    echo "Installing PHP modules"
    apt -qq update
    apt install -qqy php php-fpm php7.3-mysql php-xml
  else
    echo "PHP and PHP-FPM installed"
  fi
    echo "Configuring PHP for Caddy"
    sed -i 's/www-data/caddy/g' /etc/php/7.3/fpm/pool.d/www.conf
    systemctl restart php7.3-fpm.service
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

install_edit_birdnet_conf() {
  cat << EOF > /etc/systemd/system/edit_birdnet_conf.service
[Unit]
Description=Edit birdnet.conf

[Service]
Restart=on-failure
RestartSec=3
Type=simple
User=pi
Environment=TERM=xterm-256color
ExecStart=/usr/local/bin/gotty -w -p 9898 --title-format "Edit birdnet.conf" nano /home/pi/BirdNET-Pi/birdnet.conf

[Install]
WantedBy=multi-user.target
EOF
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
  if [ ! -d /usr/share/NX ];then
    echo "Installing NoMachine"
    curl -s -o ${HOME}/nomachine.deb -O "${nomachine_url}"
    apt install -y ${HOME}/nomachine.deb
    rm -f ${HOME}/nomachine.deb
  fi
}

install_cleanup_cron() {
  echo "Installing the cleanup.cron"
  if ! crontab -u ${USER} -l &> /dev/null;then
    crontab -u ${USER} $(dirname ${my_dir})/templates/cleanup.cron &> /dev/null
  else
    crontab -u ${USER} -l > ${tmpfile}
    cat $(dirname ${my_dir})/templates/cleanup.cron >> ${tmpfile}
    crontab -u ${USER} "${tmpfile}" &> /dev/null
  fi
}

install_selected_services() {
  set_hostname
  install_scripts
  install_birdnet_analysis

  if [[ "${DO_EXTRACTIONS}" =~ [Yy] ]];then
    install_extraction_service
  fi

  if [[ "${DO_RECORDING}" =~ [Yy] ]];then
    install_alsa
    install_recording_service
  fi

    install_caddy
    install_Caddyfile
    update_etc_hosts
    install_avahi_aliases
    install_gotty_logs
    install_sox
    install_mariadb
    install_php
    install_spectrogram_service
    install_edit_birdnet_conf
    install_pushed_notifications

  if [ ! -z "${ICE_PWD}" ];then
    install_icecast
    install_livestream_service
  fi

  if [[ "${INSTALL_NOMACHINE}" =~ [Yy] ]];then
    install_nomachine
  fi

  create_necessary_dirs
  install_cleanup_cron
}

if [ -f ${config_file} ];then 
  source ${config_file}
  install_selected_services
else
  echo "Unable to find a configuration file. Please make sure that $config_file exists."
fi
