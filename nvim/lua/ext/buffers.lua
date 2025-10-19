-- buffers.lua
--
-- adds custom names to buffers
-- <leader>fb shows open buffers, with a custom name if exists
-- useful for naming terminals
--
local Find = require 'ext/find'

local Telescope = require("telescope.builtin")

return {
  find_all = function()
    Telescope.buffers(Find.vertical_layout("Open Buffers", {}))
  end,

  close_other_buffers = function()
    local current_buf = vim.api.nvim_get_current_buf()

    for _, buf in ipairs(vim.api.nvim_list_bufs()) do
      if vim.api.nvim_buf_is_loaded(buf) and buf ~= current_buf then
        local success, err = pcall(function()
          vim.api.nvim_buf_delete(buf, {force = true})
        end)

        if not success then
          print("Error closing buffer " .. buf .. ": " .. tostring(err))
        else
          vim.api.nvim_feedkeys(vim.api.nvim_replace_termcodes(":", true, false, true) .. vim.api.nvim_replace_termcodes("<Esc>", true, false, true), "n", true)
        end
      end
    end
  end,

  move_left = function()
    require('bufferline').move(-1)
  end,

  move_right = function()
    require('bufferline').move(1)
  end,

}

