vim.g.python3_host_prog = (require 'ext/run').venv_python()
vim.g.mapleader = ' '
vim.opt.fixendofline = false

vim.opt.tabstop = 4       -- Number of visual spaces per TAB
vim.opt.shiftwidth = 4    -- Number of spaces to use for autoindent
vim.opt.softtabstop = 4   -- Number of spaces to use for autoindent
vim.opt.expandtab = true  -- Use spaces instead of tabs

vim.opt.clipboard = 'unnamedplus'
vim.opt.number = true
vim.opt.relativenumber = true
vim.opt.smoothscroll = true
vim.opt.timeoutlen = 200
vim.opt.ignorecase = true
vim.opt.smartcase = true

vim.opt.foldmethod = "indent"
-- default is "#", which makes indent folding hand '#' lines the level of their
-- surroundings instead of their own indent. That is meant for C preprocessor
-- directives; in shell/python/ruby it silently drops every comment out of its
-- enclosing fold.
vim.opt.foldignore = ""
-- without this, indent folding opens every file fully collapsed
-- vim.opt.foldlevelstart = 99

vim.api.nvim_create_autocmd("User", {
  pattern = "VeryLazy",
  once = true,
  callback = function()
    require 'mappings'
    require 'snippets'
  end,
})

require 'plugins'
require 'autocmd'
require 'ui'
require 'ext/mymath'
require 'ext/mysnips'

require('ext/coderunner').setup_autocmds()
require('ext/clipboard').setup_autocmds()

if #vim.api.nvim_list_uis() == 0 then return end

function setup_transparency()
vim.cmd [[
  highlight Normal      ctermbg=none guibg=none
  highlight NormalNC    ctermbg=none guibg=none
  highlight SignColumn  ctermbg=none guibg=none
  highlight VertSplit   ctermbg=none guibg=none
  highlight StatusLine  ctermbg=none guibg=none
  highlight LineNr      ctermbg=none guibg=none
  highlight EndOfBuffer ctermbg=none guibg=none
]]
end
setup_transparency()

-- no "folds": mkview would persist foldmethod/foldlevel/manual folds and
-- loadview would replay them, so fold state would drift between sessions
vim.opt.viewoptions = { "cursor", "curdir", "slash", "unix" }

