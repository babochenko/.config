if #vim.api.nvim_list_uis() == 0 then return end

vim.diagnostic.config({
  virtual_text = false,  -- Disable inline virtual text
  signs = true,          -- Keep gutter signs
  underline = true,      -- Keep underline
  update_in_insert = false, -- Disable updates in insert mode
  severity_sort = true,  -- Sort by severity
  float = { border = "rounded" }, -- Customize floating windows
})

vim.api.nvim_create_autocmd("User", {
  pattern = "VeryLazy",
  once = true,
  callback = function()
    require('telescope').setup {
      defaults = {
        previewer = true,
        borderchars = { '─', '│', '─', '│', '╭', '╮', '╯', '╰' },
        win_options = { winblend = 10 },
        border = true,
        layout_strategy = 'horizontal',
        layout_config = {
          horizontal = { prompt_position = 'top', preview_width = 0.5, results_width = 0.8 },
          vertical = { mirror = false },
          width = 0.87,
          height = 0.80,
          preview_cutoff = 120,
        },
        sorting_strategy = 'ascending',
      },
    }
  end,
})

-- file position as a bar + percentage, e.g.  ████▌░░░░░  45%
local BAR_WIDTH   = 10
local BAR_FULL    = '█'
local BAR_EMPTY   = '░'
local BAR_PARTIAL = { '▏', '▎', '▍', '▌', '▋', '▊', '▉' }

local function progress_bar()
  local cur   = vim.fn.line('.')
  local total = vim.fn.line('$')
  local frac  = total > 1 and (cur - 1) / (total - 1) or 1

  local filled = frac * BAR_WIDTH
  local full   = math.floor(filled)

  local bar = string.rep(BAR_FULL, full)
  if full < BAR_WIDTH then
    -- sub-cell remainder, so the bar moves smoothly line by line
    local idx = math.floor((filled - full) * (#BAR_PARTIAL + 1))
    bar = bar .. (idx > 0 and BAR_PARTIAL[idx] or BAR_EMPTY)
    bar = bar .. string.rep(BAR_EMPTY, BAR_WIDTH - full - 1)
  end

  -- %%%% -> a literal "%%" in the returned string, which the statusline
  -- renders as one "%"; a bare "%" would be read as a statusline item (E539)
  return string.format('%s %3d%%%%', bar, math.floor(frac * 100))
end

require('lualine').setup {
  options = {
    icons_enabled = true,
    theme = 'onedark',
    component_separators = { left = '', right = ''},
    section_separators = { left = '', right = ''},
    disabled_filetypes = {
      statusline = {},
      winbar = {},
    },
    ignore_focus = {},
    always_divide_middle = true,
    always_show_tabline = true,
    globalstatus = false,
    refresh = {
      statusline = 100,
      tabline = 100,
      winbar = 100,
    }
  },
  sections = {
    lualine_a = {'mode'},
    lualine_b = {'branch', 'diff', 'diagnostics'},
    lualine_c = {'filename'},
    lualine_x = {'encoding', 'fileformat', 'filetype'},
    lualine_y = {progress_bar},
    lualine_z = {'location'}
  },
  inactive_sectioms = {
    lualine_a = {},
    lualine_b = {},
    lualine_c = {'filename'},
    lualine_x = {'location'},
    lualine_y = {},
    lualine_z = {}
  },
  tabline = {},
  winbar = {},
  inactive_winbar = {},
  extensions = {}
}

require('render-markdown').setup({
    latex = {
        enabled = true,
        render_modes = false,
        converter = { 'utftex', 'latex2text' },
        inline = true,
        block = true,
        highlight = 'RenderMarkdownMath',
        position = 'center',
        top_pad = 0,
        bottom_pad = 0,
    },
})

local hl_group = function(group, opts)
  vim.api.nvim_set_hl(0, group, opts)
end

local neutral = "#abb2bf"
local border = "#657088"
local keyword = "#61afef"
local constant = "#c678dd"

-- current line number in the cursor's accent colour; "number" keeps the line
-- background untouched. Mirrors ghostty's cursor-color, which wins over the
-- OSC 12 nvim sends for the Cursor group - keep the two in sync by hand.
local cursor_accent = "#ffcc00"

vim.opt.cursorline = true
vim.opt.cursorlineopt = "number"

hl_group("CursorLineNr", { fg = cursor_accent, bold = true })

hl_group("TelescopeBorder", { fg = border, bg = "#1c1f26" })
hl_group("@module", { fg = neutral })
hl_group("@property", { fg = neutral })
hl_group("@variable", { fg = neutral })
hl_group("@variable.member", { fg = neutral })
hl_group("@variable.parameter", { fg = neutral })

hl_group("@keyword", { fg = keyword })
hl_group("@lsp.type.modifier.java", { link = "@keyword" })
hl_group("@keyword.return", { link = "@keyword" })
hl_group("@keyword.operator", { fg = neutral })
hl_group("@constant", { fg = constant })
hl_group("@lsp.mod.static.java", { fg = constant })

hl_group("@punctuation.bracket", { fg = neutral })
hl_group("@punctuation.delimiter", { fg = border })

