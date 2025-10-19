#!/bin/bash
nvim --headless \
  -c "lua require('lazy').load({plugins = {'plenary.nvim'}})" \
  -c "PlenaryBustedDirectory tests/" \
  -c "qa"

