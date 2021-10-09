#!/usr/bin/env sh

file_name="entertainment-decider.desktop"
scheme="entertainment-decider"

python3 app.py misc generate-desktop-file > ~/.local/share/applications/$file_name
xdg-mime default $file_name x-scheme-handler/$scheme
