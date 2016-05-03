#packages needed
execute 'apt-get update'
package 'vim'
package 'postgresql-9.4'
package 'postgresql-9.4-debversion'
package 'python-argparse'
package 'python-debian'
package 'python-debianbts'
package 'python-inotifyx'
package 'python-paste'
package 'python-psycopg2'
package 'python-pyramid'
package 'python-sqlalchemy'
package 'python-subversion'
package 'python-pip'
package 'wget'

#installing dependency that has no package on debian
execute 'pip install pyramid_chameleon'

#creating user pet
user 'pet' do
  action :create
end

#replacing config files and restarting postgres
cookbook_file '/etc/postgresql/9.4/main/postgresql.conf' do
  owner 'postgres'
  group 'postgres'
  mode '644'
  action :create
end

cookbook_file '/etc/postgresql/9.4/main/pg_hba.conf' do
  owner 'postgres'
  group 'postgres'
  mode '640'
  action :create
end

service 'postgresql' do
  action [:restart, :enable]
end

#creating user and database
execute "create pet user" do
  command "createuser pet"
  user "postgres"
  action :run
  not_if "psql postgres -tAc \"SELECT 1 FROM pg_roles WHERE rolname='pet'\" | grep -q 1"
end
#
execute "createdb -O pet pet" do
  user "postgres"
  action :run
  not_if 'psql -lqt | cut -d \| -f 1 | grep -qw pet'
end


execute "implements debversion types" do
  command "psql pet < /usr/share/postgresql/9.4/contrib/debversion.sql"
  user "postgres"
  action :run
end

#adding config file for hosts and restarting postgres
cookbook_file '/etc/hosts' do
  owner 'root'
  group 'root'
  mode '644'
  action :create
end

service 'postgresql' do
  action :restart
end

#updating schema and inserting data
execute "update schema and creating tables" do
  command "/vagrant/pet-update -c"
  user "pet"
  action :run
  not_if "psql pet -tAc \"SELECT 1 FROM team\" | grep -q 1"
end

execute "database insert team table" do
  command "psql pet --command \"INSERT INTO team (name, maintainer, url) VALUES ('pkg-perl', 'Debian Perl Group <pkg-perl-maintainers@lists.alioth.debian.org>', 'http://pkg-perl.alioth.debian.org/');\""
  user "pet"
  action :run
  not_if "psql pet -tAc \"SELECT * FROM team WHERE name='pkg-perl'\" | grep -q 'pkg-perl'"
end

execute "database insert repository table" do
  command "psql pet --command \"INSERT INTO repository (name, type, root, web_root, team_id) VALUES ('git','git','https://pet.alioth.debian.org/pet2-data/pkg-perl/git-pkg-perl-packages.json','http://anonscm.debian.org/gitweb/?p=pkg-perl/packages', 1);\""
  user "pet"
  action :run
  not_if "psql pet -tAc \"SELECT * FROM repository WHERE name='git'\" | grep -q 'git'"
end

execute "database insert package table" do
  command "psql pet --command \"INSERT INTO package (name, repository_id) VALUES ('clive', 1);\""
  user "pet"
  action :run
  not_if "psql pet -tAc \"SELECT * FROM package WHERE name='clive'\" | grep -q 'clive'"
end

execute "database insert archive table" do
  command "psql pet --command \"INSERT INTO archive (name, url, web_root) VALUES ('debian', 'http://cdn.debian.net/debian', 'http://packages.qa.debian.org/');\""
  user "pet"
  action :run
  not_if "psql pet -tAc \"SELECT * FROM archive WHERE name='debian'\" | grep -q 'debian'"
end

execute "database insert suite table" do
  command "psql pet --command \"INSERT INTO suite (archive_id, name) VALUES (1, 'unstable');\""
  user "pet"
  action :run
  not_if "psql pet -tAc \"SELECT * FROM suite WHERE name='unstable'\" | grep -q 'unstable'"
end
