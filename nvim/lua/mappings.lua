local DIA = vim.diagnostic
local GS = require 'gitsigns'
local BUFLINE = require 'bufferline'
local KEYS = require 'which-key'

local Find = require 'ext/find'
local Buf = require 'ext/buffers'
local Code = require 'ext/code'
local Mark = require 'ext/marks'
local Sys = require 'ext/system'
local Db = require 'ext/db'
local CodeRunner = require 'ext/coderunner'
local Clipboard = require 'ext/clipboard'

local map = vim.keymap.set

local function group(prefix, name)
    KEYS.add({{ prefix, name = name }})
end

local function nvimTree()
    vim.cmd("NvimTreeFindFileToggle")
    vim.cmd("normal! zz")
end

local nvim_defaults = {
  map('n', '<leader>el', function() vim.cmd('edit ~/.local/state/nvim/lsp.log') end, { desc = 'open LSP logs' }),
  map('n', '<leader>en', function() vim.cmd('edit ~/.local/share/nvim/notes.md') end, { desc = 'open notes' }),
  map('n', ',', '*'),
}

local general_helpers = {
  -- map({'n', 'v', 'c', 'o', 's'}, ',', '<CR>'),
  map('n', 'gb', '%' , { desc = 'goto matching bracket' }),
  map('n', '<leader>o', Sys.open_system, { desc = 'open this file in system viewer' }),
  map('n', '<leader>tm', Sys.toggle_mouse, { silent = true, desc = 'toggle mouse' }),
  map('n', ';', ':', { desc = 'command mode' }),
  map('n', '<Esc>', '<cmd>noh<CR>', { desc = 'general clear highlights' }),
  map('n', '<leader>db', ':DBUI<CR>', { desc = 'open database ui' }),
  map('n', '<leader>dc', Db.open_config_file, { desc = 'open database config' }),
  map('n', '<leader>fo', ":!open -R %:p:h<CR>", { desc = 'Open this in file manager' }),
  map('n', '<leader>fO', ":!open .<CR>", { desc = 'Open current dir in file manager' }),
  map('n', '<leader>fp', Sys.copy_file_path, { desc = 'show file path' }),
  map('n', '<leader>fP', Sys.copy_file_name, { desc = 'show file name' }),
  map({'n', 'v'}, '<leader>fl', Code.format_file, { desc = 'lint file' }),
}

local buffers = {
  create = {
    group('<leader>n', 'New'),
    map('n', '<leader>nn', ':enew<CR>', { desc = 'New file' }),
    group('<leader>t', 'Terminal'),
    map('n', '<leader>tt', ':term<CR>', { desc = 'New term' }),
  },
  modify = {
    group('<leader>b', 'Buffers'),
    map('n', '<leader>bn', Buf.move_right, { desc = 'Move buffer right' }),
    map('n', '<leader>bp', Buf.move_left, { desc = 'Move buffer left' }),
    map('n', '<leader>fb', Buf.find_all, { desc = 'Find buffers' }),
  },
}

local code = {
  group('<leader>c', 'Code'),
  navigate = {
    map('n', '<leader>cs', vim.lsp.buf.signature_help, { desc = 'function signature' }),
    map('n', '<leader>ch', vim.lsp.buf.hover, { desc = 'function help' }),
    map('n', '<leader>cd', function() DIA.open_float(nil, { focusable = false }) end, { desc = 'line diagnostics' }),
    map('n', '<leader>cD', vim.diagnostic.setloclist, { desc = 'all diagnostics' }),
    map('n', '<leader>cn', DIA.goto_next, { desc = 'next diagnostic' }),
    map('n', '<leader>cp', DIA.goto_prev, { desc = 'prev diagnostic' }),
    map('n', 'gd', vim.lsp.buf.definition, { desc = 'goto definition' }),
    map('n', 'gu', Find.usages, { desc = 'goto usages' }),
    map('n', 'gi', Find.impls, { desc = 'goto implementations' }),
  },
  edit = {
    map('n', 'cr', vim.lsp.buf.rename, { desc = 'rename symbol' }),
    map('n', '<leader>/', 'gcc', { desc = 'toggle comment', remap = true }),
    map('v', '<leader>/', 'gc', { desc = 'toggle comment', remap = true }),
  },
  run = {
    group('<leader>r', 'Run'),
    map('n', '<leader>rr', CodeRunner.do_test_line, { desc = 'Run this line' }),
    map('n', '<leader>ra', CodeRunner.do_test_file, { desc = 'Run tests in file' }),
    map('n', '<leader>rf', CodeRunner.do_run_file, { desc = 'Run file' }),
    -- map('n', '<leader>rf', Code.run_file, { desc = 'execute file' }),
  },
}

local tabs = {
  map('n', '<C-h>', '<C-w>h', { desc = 'switch window left' }),
  map('n', '<C-l>', '<C-w>l', { desc = 'switch window right' }),
  map('n', '<C-j>', '<C-w>j', { desc = 'switch window down' }),
  map('n', '<C-k>', '<C-w>k', { desc = 'switch window up' }),
  map('t', '<C-x>', '<C-\\><C-N>', { desc = 'terminal escape terminal mode' }),
  map('n', '<tab>', function() BUFLINE.cycle(1) end, { desc = 'buffer goto next' }),
  map('n', '<S-tab>', function() BUFLINE.cycle(-1) end, { desc = 'buffer goto prev' }),
  map('n', '<leader>x', ':bdelete<CR>', { desc = 'close buffer' }),
  map('n', '<leader>X', Buf.close_other_buffers, { desc = 'close other buffers' }),
  map('n', '<leader>q', '<C-W>q', { desc = 'close window' }),
  map('n', '<C-n>', nvimTree, { desc = 'nvimtree' }),
}

local search = {
  group('<leader>f', 'Find'),
  map('n', '<leader>ff', Find.files, { desc = 'Find files' }),
  map('n', '<leader>fa', '<cmd>Telescope find_files follow=true no_ignore=true hidden=true<CR>', { desc = 'Find all files' }),

  map('n', '<leader>fw', Find.words_literal, { desc = 'Find words' }),
  map('n', '<leader>fz', '<cmd>Telescope current_buffer_fuzzy_find<CR>', { desc = 'Find words in current file' }),
  map('n', '<leader>fW', Find.words, { desc = 'Grep words' }),

  map('n', '<leader>ft', Find.testfile, { desc = 'Find test file' }),
  map('n', '<leader>fh', Find.files_history, { desc = 'Files history' }),
  map('n', '<leader>fH', Find.all_files_history, { desc = 'Files history everywhere' }),
  map('n', '<leader>p', Clipboard.show_clipboard_history, { desc = 'Clipboard history' }),
  map('n', '<leader>P', function() vim.cmd('edit ' .. Clipboard.get_clipboard_file()) end, { desc = 'Clipboard history' }),

  map('n', '<leader>fs', Find.snippets_current, { desc = 'Find snippets for this file' }),
  map('n', '<leader>fS', Find.snippets_all, { desc = 'Find all snippets' }),

}

local git = {
  group('<leader>g', 'Git'),
  map('n', '<leader>gb', GS.blame, { desc = 'Git blame' }),
  map('n', '<leader>gc', ":Git add . | Git commit<CR>", { desc = 'Git commit' }),
  map('n', '<leader>gl', GS.blame_line, { desc = 'Git blame this line' }),
  map({'n', 'v'}, '<leader>gr', GS.reset_hunk, { desc = 'Git reset hunk' }),
  map({'n', 'v'}, '<leader>gp', GS.preview_hunk, { desc = 'Git preview hunk' }),
  map('n', '<leader>gd', ':DiffviewOpen<CR>', { desc = 'Git diffthis' }),
  map('n', '<leader>gh', ':DiffviewFileHistory %<CR>', { desc = 'Git History' }),
  map('n', '<leader>gH', ':DiffviewFileHistory %:p<CR>', { desc = 'Git History this file' }),
  map('n', '<leader>gs', ':Git<CR>', { desc = 'Git Status' }),
  map('n', '<leader>gg', '<cmd>Flog<CR>', { desc = 'Git Graph' }),
}

local marks = {
  group('<leader>m', 'Marks'),
  map('n', '<leader>mm', Mark.toggle_mark, { desc = 'Toggle mark' }),
  map('n', '<leader>mn', Mark.name_mark, { desc = 'Name this mark' }),
  map('n', '<leader>mf', Mark.open_mark_file, { desc = 'Open mark file' }),
  map('n', '<leader>fm', Mark.list_marks, { desc = 'Find marks' }),
  map('n', '<leader>fM', Mark.list_all_marks, { desc = 'Find marks everywhere' }),
}

