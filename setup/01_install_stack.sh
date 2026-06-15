#!/usr/bin/env bash
set -e
# Run with sudo privileges. Either run as: sudo ./01_install_stack.sh
# or export your password: SUDO_PW=yourpassword ./01_install_stack.sh
PW="${SUDO_PW:-}"
echo "$PW" | sudo -S bash -c '
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq software-properties-common curl unzip git
add-apt-repository -y ppa:ondrej/php
apt-get update -qq
apt-get install -y -qq apache2 mariadb-server \
  php8.1 libapache2-mod-php8.1 php8.1-cli \
  php8.1-mysql php8.1-xml php8.1-curl php8.1-gd php8.1-intl php8.1-mbstring \
  php8.1-soap php8.1-zip php8.1-xmlrpc php8.1-bcmath php8.1-ldap php8.1-sodium \
  python3-pip python3-venv nginx
'
echo "STACK_INSTALL_DONE"
