Exec { path => '/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin' }

include timezone
include user
include apt
include mysql
include python
include pildeps
include software

class timezone {
  package { "tzdata":
    ensure => latest,
    require => Class['apt']
  }

  file { "/etc/localtime":
    require => Package["tzdata"],
    source => "file:///usr/share/zoneinfo/${tz}",
  }
}

class user {
  exec { 'add user':
    command => "sudo useradd -m -G sudo -s /bin/bash ${user}",
    unless => "id -u ${user}"
  }

  exec { 'set password':
    command => "echo \"${user}:${password}\" | sudo chpasswd",
    require => Exec['add user']
  }

}

class apt {
  exec { 'apt-get update':
    timeout => 0
  }

  package { 'python-software-properties':
    ensure => latest,
    require => Exec['apt-get update']
  }

  exec { 'last ppa':
    command => 'add-apt-repository ppa:git-core/ppa',
    require => Package['python-software-properties']
  }

  exec { 'apt-get update again':
    command => 'apt-get update',
    timeout => 0,
    require => Exec['last ppa']
  }
}

class mysql {
  $create_db_cmd = "CREATE DATABASE ${db_name} CHARACTER SET utf8;"
  $create_user_cmd = "CREATE USER '${db_user}'@localhost IDENTIFIED BY '${db_password}';"
  $grant_db_cmd = "GRANT ALL PRIVILEGES ON ${db_name}.* TO '${db_user}'@localhost;"

  package { 'mysql-server':
    ensure => latest,
    require => Class['apt']
  }

  package { 'libmysqlclient-dev':
    ensure => latest,
    require => Class['apt']
  }

  service { 'mysql':
    ensure => running,
    enable => true,
    require => Package['mysql-server']
  }

  exec { 'grant user db':
    command => "mysql -u root -e \"${create_db_cmd}${create_user_cmd}${grant_db_cmd}\"",
    unless => "mysqlshow -u${db_user} -p${db_password} ${db_name}",
    require => Service['mysql']
  }
}

class python {
  package { 'curl':
    ensure => latest,
    require => Class['apt']
  }

  package { 'python':
    ensure => latest,
    require => Class['apt']
  }

  package { 'python-dev':
    ensure => latest,
    require => Class['apt']
  }

  exec { 'install-pip':
    command => 'curl https://bootstrap.pypa.io/get-pip.py | python',
    require => Package['python', 'curl']
  }
}

class pildeps {
  package { ['python-imaging', 'libjpeg-dev', 'libfreetype6-dev']:
    ensure => latest,
    require => Class['apt'],
    before => Exec['pil png', 'pil jpg', 'pil freetype']
  }

  exec { 'pil png':
    command => 'sudo ln -s /usr/lib/`uname -i`-linux-gnu/libz.so /usr/lib/',
    unless => 'test -L /usr/lib/libz.so'
  }

  exec { 'pil jpg':
    command => 'sudo ln -s /usr/lib/`uname -i`-linux-gnu/libjpeg.so /usr/lib/',
    unless => 'test -L /usr/lib/libjpeg.so'
  }

  exec { 'pil freetype':
    command => 'sudo ln -s /usr/lib/`uname -i`-linux-gnu/libfreetype.so /usr/lib/',
    unless => 'test -L /usr/lib/libfreetype.so'
  }
}

class software {
  package { 'git':
    ensure => latest,
    require => Class['apt']
  }

  package { 'vim':
    ensure => latest,
    require => Class['apt']
  }
}
