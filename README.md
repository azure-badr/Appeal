# Appeal
A Discord app that allows users to appeal their bans on your server.

## `bot`
The bot directory in this repository contains the main bot app that is used through Discord. It allows server managers to manage bans by accepting or rejecting individual bans.

### Bot commands
`.accept` - Accepts a ban appeal and unbans the user from the server.  
`.reject  <duration in months>` - Rejects a ban appeal for a set amount of time. e.g.  
`.reject 3` would reject the ban appeal for 3 months. The user could appeal after 3 months.  
`.reject 0` would permanently reject the appeal.

## `client`
The client directory contains a Quart app linked with the Discord app that provides a web interface for users to appeal their bans and see the status of their appeals.

When an appeal is created, it:
1. Creates a thread on a server for server managers to discuss the ban
2. Redirects user to a page showing the status of their ban (pending/accepted/rejected)
