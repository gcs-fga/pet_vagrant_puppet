#!/usr/bin/env sh
echo "Initial apt-get update..."
apt-get update >/dev/null
REPO_DEB_URL="http://apt.puppetlabs.com/puppetlabs-release-jessie.deb"
echo "Installing wget..."
apt-get --yes install wget >/dev/null
echo "Configuring PuppetLabs repo..."
repo_deb_path=$(mktemp)
wget --output-document="${repo_deb_path}" "${REPO_DEB_URL}" 2>/dev/null
dpkg -i "${repo_deb_path}" >/dev/null
rm "${repo_deb_path}"
apt-get update >/dev/null
echo "Installing Puppet..."
DEBIAN_FRONTEND=noninteractive apt-get -y  install puppet >/dev/null
echo "Puppet installed!"
