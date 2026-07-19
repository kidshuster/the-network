network create <nkey> <name> <announcement channel>
network init
network delete <nkey>
network status
network list

server create <nkey> <server name> <profile image> <display name>
server delete <nkey> <server name> 
server enable <nkey> <server name>
server disable <nkey> <server name>
server status <nkey>
server list <nkey>
server list

profile update <display name> <profile image>  (partner role, in profile thread only)

On a blank guild, run `/network init` first to create hub categories (**Subscribe To Me!**, **The Network**, **Moderation**), move/create rules and moderator channels, and sync role permissions. Then `/network create` provisions feed categories and join channels.
