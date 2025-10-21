-- lua/fold_current.lua
local M = {}

-- node types worth folding (add more as you like)
local TARGETS = {
  "function_definition","function_declaration","method_definition","method_declaration",
  "class_declaration","class_definition","interface_declaration","struct_specifier",
  "if_statement","switch_statement","for_statement","while_statement","do_statement",
  "block","table_constructor","object","array","module","namespace_definition"
}

local function ts_node_at_cursor()
  local ok, ts = pcall(require, "nvim-treesitter.ts_utils")
  if not ok then return nil end
  return ts.get_node_at_cursor()
end

local function is_target(node)
  local t = node:type()
  for _, x in ipairs(TARGETS) do if t == x then return true end end
  return false
end

local function nearest_target(node)
  while node do
    if is_target(node) then return node end
    node = node:parent()
  end
end

local function fold_range(sr, er)
  -- Use Tree-sitter folds and close just this region.
  vim.opt_local.foldmethod = "expr"
  vim.opt_local.foldexpr = "nvim_treesitter#foldexpr()"
  vim.opt_local.foldenable = true

  -- Temporarily set cursor to start, close fold under cursor, restore cursor.
  local win = vim.api.nvim_get_current_win()
  local cur = vim.api.nvim_win_get_cursor(win)
  vim.api.nvim_win_set_cursor(win, { sr + 1, 0 })
  vim.cmd.normal({ args = { "zc" }, bang = true })  -- close fold at cursor
  vim.api.nvim_win_set_cursor(win, cur)
end

function M.fold_current()
  local node = ts_node_at_cursor()
  if node then
    local target = nearest_target(node)
    if target then
      local sr, _, er, _ = target:range()     -- 0-based, end exclusive
      fold_range(sr, er - 1)
      print("Folded current code element")
      return
    end
  end
  -- Fallback to LSP folding ranges if TS not available / no node.
  if #vim.lsp.get_active_clients({ bufnr = 0 }) > 0 then
    local params = { textDocument = vim.lsp.util.make_text_document_identifier(0) }
    local resp = vim.lsp.buf_request_sync(0, "textDocument/foldingRange", params, 500)
    local pos = vim.api.nvim_win_get_cursor(0)
    local line = pos[1] - 1
    for _, r in pairs(resp or {}) do
      for _, fr in ipairs(r.result or {}) do
        local s = fr.startLine
        local e = (fr.endLine or s)
        if line >= s and line <= e then
          fold_range(s, e)
          print("Folded via LSP range")
          return
        end
      end
    end
  end
  print("No foldable element found here")
end

function M.open_current()
  vim.cmd.normal({ args = { "zo" }, bang = true })
end

function M.open_all()
  vim.opt_local.foldenable = true
  vim.cmd("zR")
end

function M.close_all()
  vim.opt_local.foldenable = true
  vim.cmd("zM")
end

return M

