local telescope = require('telescope')
local pickers = require('telescope.pickers')
local finders = require('telescope.finders')
local conf = require('telescope.config').values
local actions = require('telescope.actions')
local action_state = require('telescope.actions.state')

local function get_clipboard_file()
  local env_path = os.getenv('NVIM_CLIPBOARD_HISTORY')
  if env_path then
    return env_path
  end
  
  local home = os.getenv('HOME') or os.getenv('USERPROFILE')
  return home .. '/.nvim_clipboard_history'
end

local function read_clipboard_history()
  local file_path = get_clipboard_file()
  local file = io.open(file_path, 'r')
  if not file then
    return {}
  end
  
  local history = {}
  for line in file:lines() do
    if line ~= '' then
      table.insert(history, line)
    end
  end
  file:close()
  
  return history
end

local function write_clipboard_history(history)
  local file_path = get_clipboard_file()
  local file = io.open(file_path, 'w')
  if not file then
    return false
  end
  
  for _, entry in ipairs(history) do
    file:write(entry .. '\n')
  end
  file:close()
  return true
end

local function add_to_clipboard_history(text)
  local history = read_clipboard_history()
  
  -- Remove duplicates if exists
  for i, entry in ipairs(history) do
    if entry == text then
      table.remove(history, i)
      break
    end
  end
  
  -- Add to beginning (most recent first)
  table.insert(history, 1, text)
  
  -- Limit history size to 100 entries
  if #history > 100 then
    for i = 101, #history do
      history[i] = nil
    end
  end
  
  write_clipboard_history(history)
end

local function setup_autocmds()
  vim.api.nvim_create_autocmd('TextYankPost', {
    group = vim.api.nvim_create_augroup('ClipboardHistory', { clear = true }),
    callback = function()
      local text = vim.fn.getreg('"')
      if text and text ~= '' and #text > 0 then
        add_to_clipboard_history(text)
      end
    end,
  })
end

local function insert_text_at_cursor(text)
  local pos = vim.api.nvim_win_get_cursor(0)
  local lines = vim.split(text, '\n')

  if #lines == 1 then
    local current_line = vim.api.nvim_get_current_line()
    local new_line = current_line:sub(1, pos[2]) .. text .. current_line:sub(pos[2] + 1)
    vim.api.nvim_set_current_line(new_line)
    vim.api.nvim_win_set_cursor(0, {pos[1], pos[2] + #text})
  else
    lines[1] = vim.api.nvim_get_current_line():sub(1, pos[2]) .. lines[1]
    lines[#lines] = lines[#lines] .. vim.api.nvim_get_current_line():sub(pos[2] + 1)
    vim.api.nvim_buf_set_lines(0, pos[1] - 1, pos[1], false, lines)
    vim.api.nvim_win_set_cursor(0, {pos[1] + #lines - 1, #lines[#lines] - #vim.api.nvim_get_current_line():sub(pos[2] + 1)})
  end
end

local function insert_multiple_entries_at_cursor(entries)
  local pos = vim.api.nvim_win_get_cursor(0)
  local current_line = vim.api.nvim_get_current_line()

  -- Create lines to insert: each entry on its own line
  local lines_to_insert = {}

  -- First line: current line up to cursor + first entry
  lines_to_insert[1] = current_line:sub(1, pos[2]) .. entries[1]

  -- Middle lines: remaining entries
  for i = 2, #entries do
    table.insert(lines_to_insert, entries[i])
  end

  -- Last line: add the rest of the current line after cursor
  local rest_of_line = current_line:sub(pos[2] + 1)
  if rest_of_line ~= '' then
    table.insert(lines_to_insert, rest_of_line)
  end

  -- Replace the current line with all our new lines
  vim.api.nvim_buf_set_lines(0, pos[1] - 1, pos[1], false, lines_to_insert)

  -- Move cursor to end of inserted content
  local final_row = pos[1] + #entries - 1
  local final_col = #entries[#entries]
  if rest_of_line == '' then
    final_col = #lines_to_insert[#lines_to_insert]
  end
  vim.api.nvim_win_set_cursor(0, {final_row, final_col})
end

local function copy_to_clipboard(text)
  vim.fn.setreg('+', text)
  vim.fn.setreg('"', text)
  print('Copied to clipboard')
end

local function show_clipboard_history()
  local history = read_clipboard_history()

  if #history == 0 then
    print('Clipboard history is empty')
    return
  end

  pickers.new({}, {
    prompt_title = 'Clipboard History (Tab to select multiple)',
    finder = finders.new_table({
      results = history,
      entry_maker = function(entry)
        local display = entry:gsub('\n', '\\n'):sub(1, 80)
        if #entry > 80 then
          display = display .. '...'
        end
        return {
          value = entry,
          display = display,
          ordinal = entry,
        }
      end,
    }),
    sorter = conf.generic_sorter({}),
    attach_mappings = function(prompt_bufnr, map)
      actions.select_default:replace(function()
        local picker = action_state.get_current_picker(prompt_bufnr)
        local multi_selection = picker:get_multi_selection()

        actions.close(prompt_bufnr)

        if #multi_selection > 0 then
          -- Extract values from multi-selection
          local entries = {}
          for _, selection in ipairs(multi_selection) do
            table.insert(entries, selection.value)
          end
          insert_multiple_entries_at_cursor(entries)
        else
          -- Single selection fallback
          local selection = action_state.get_selected_entry()
          if selection then
            insert_text_at_cursor(selection.value)
          end
        end
      end)

      -- Tab key for multiselect
      map('i', '<Tab>', actions.toggle_selection + actions.move_selection_next)
      map('n', '<Tab>', actions.toggle_selection + actions.move_selection_next)

      -- Shift-Tab for multiselect previous
      map('i', '<S-Tab>', actions.toggle_selection + actions.move_selection_previous)
      map('n', '<S-Tab>', actions.toggle_selection + actions.move_selection_previous)

      map('i', '<C-y>', function()
        local selection = action_state.get_selected_entry()
        if selection then
          copy_to_clipboard(selection.value)
        end
      end)

      map('n', '<C-y>', function()
        local selection = action_state.get_selected_entry()
        if selection then
          copy_to_clipboard(selection.value)
        end
      end)

      return true
    end,
  }):find()
end

return {
  get_clipboard_file = get_clipboard_file,
  show_clipboard_history = show_clipboard_history,
  setup_autocmds = setup_autocmds,
}

