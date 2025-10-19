-- inspired by https://github.com/chentoast/marks.nvi pickers = require('telescope.pickers')marks
local actions = require 'telescope.actions'

local TSC = (function ()
  local finders = require 'telescope.finders'
  local action_state = require 'telescope.actions.state'
  local previewers = require 'telescope.previewers'
  local pickers = require "telescope.pickers"
  local entry_display = require "telescope.pickers.entry_display"
  local conf = require('telescope.config').values
  local utils = require "telescope.utils"
  local strings = require "plenary.strings"

  return {
    make_table = finders.new_table,
    make_previewer = previewers.new_buffer_previewer,
    make_picker = pickers.new,
    make_displayer = entry_display.create,
    make_sorter = conf.generic_sorter,

    get_selected_entry = action_state.get_selected_entry,
    get_icon = function(file)
      local icon, hlgroup = utils.get_devicons(file, false)
      local width = strings.strdisplaywidth(icon)
      return icon, hlgroup, width
    end,
  }
end)()

local Find = require 'ext/find'

local marks_file = vim.fn.expand(vim.env.NVIM_MARKS_FILE or "~/.local/share/nvim/marks.json") -- File to save marks
local global_marks = {} -- Stores all marks with file, line, and optional name
local deleted_marks = {} -- Tracks marks that were explicitly deleted

local function load_marks_file()
  local file = io.open(marks_file, "r")
  local res = {}
  if file then
    local json = file:read("*a")
    file:close()
    if json and #json > 0 then
      res = vim.fn.json_decode(json) or {}
      -- print("Marks loaded!")
    else
      res = {}
      print("Marks file is empty.")
    end
  else
    res = {}
    print("No marks file found.")
  end
  return res
end

local function load_marks()
  global_marks = load_marks_file()
end

local function merge_marks(old, new)
  local map = {}

  -- Add old marks to the map
  for _, mark in ipairs(old) do
    local key = mark.name or (mark.file .. ":" .. mark.line)
    map[key] = mark
  end

  -- Override with new marks (global_marks has priority)
  for _, mark in ipairs(new) do
    local key = mark.name or (mark.file .. ":" .. mark.line)
    map[key] = mark
  end

  -- Remove explicitly deleted marks
  for deleted_key, _ in pairs(deleted_marks) do
    map[deleted_key] = nil
  end

  -- Convert back to array
  local merged = {}
  for _, mark in pairs(map) do
    table.insert(merged, mark)
  end

  return merged
end

local function save_marks()
  local marks = merge_marks(load_marks_file(), global_marks)
  
  local json = vim.fn.json_encode(marks)
  if json and #json > 0 then
    local file = io.open(marks_file, "w")
    if file then
      local json_f = vim.fn.system({ "jq", "sort_by(.file, .line)", "-M" }, json)
      file:write(json_f)
      file:close()
      print("Marks saved!")
    else
      print("Failed to save marks.")
    end
  else
    print("No marks to save.")
  end
end

local function toggle_mark()
  local file = vim.fn.expand("%:p") -- Get full path of the current file
  local line = vim.fn.line(".") -- Get the current line number
  local mark_exists = false

  for i, mark in ipairs(global_marks) do
    if mark.file == file and mark.line == line then
      local confirm = vim.fn.input("Remove mark? (y/n): ")
      if confirm:lower() == "y" or confirm:lower() == "yes" then
        local key = mark.name or (mark.file .. ":" .. mark.line)
        deleted_marks[key] = true
        table.remove(global_marks, i)
        vim.fn.sign_unplace("MarksGroup", { buffer = vim.fn.bufnr("%") })
        print("Mark removed from " .. file .. ":" .. line)
      else
        print("Mark removal cancelled")
      end
      mark_exists = true
      break
    end
  end

  if not mark_exists then
    local key = file .. ":" .. line
    deleted_marks[key] = nil -- Clear any previous deletion
    global_marks[#global_marks + 1] = { file = file, line = line, name = nil }
    vim.fn.sign_place(0, "MarksGroup", "MarkSign", vim.fn.bufnr("%"), { lnum = line })
    print("Mark added at " .. file .. ":" .. line)
  end

  save_marks() -- Save marks immediately
end

local marks_previewer = TSC.make_previewer({
  title = "File Preview",
  get_buffer_by_name = function(_, entry)
    return entry.value.file
  end,
  define_preview = function(self, entry)
    -- Read the file content
    local bufnr = self.state.bufnr

    -- Check if file exists and is not empty
    if not entry.value.file or entry.value.file == "" then
      vim.api.nvim_buf_set_lines(bufnr, 0, -1, false, {"Invalid file path"})
      return
    end

    -- Create file if it doesn't exist
    if not vim.fn.filereadable(entry.value.file) then
      local dir = vim.fn.fnamemodify(entry.value.file, ":h")
      vim.fn.mkdir(dir, "p")
      local file = io.open(entry.value.file, "w")
      if file then
        file:close()
      end
    end

    -- Set filetype using bo instead of nvim_buf_set_option
    vim.bo[bufnr].filetype = vim.filetype.match({ filename = entry.value.file }) or ""

    -- Load the file content
    local lines = vim.fn.readfile(entry.value.file)
    vim.api.nvim_buf_set_lines(bufnr, 0, -1, false, lines)

    -- Highlight the marked line
    local line_nr = entry.value.line
    local ns_id = vim.api.nvim_create_namespace('TelescopeMarkPreview')
    vim.api.nvim_buf_add_highlight(bufnr, ns_id, "TelescopePreviewLine", line_nr - 1, 0, -1)

    -- Center the view on the marked line
    vim.defer_fn(function()
      self.state.preview_win = vim.fn.bufwinid(bufnr)
      if self.state.preview_win ~= -1 then
        vim.api.nvim_win_set_cursor(self.state.preview_win, {line_nr, 0})
        vim.api.nvim_win_call(self.state.preview_win, function()
          vim.cmd('normal! zz')
        end)
      end
    end, 10)
  end
})

local function name_mark()
  local file = vim.fn.expand("%:p")
  local line = vim.fn.line(".")
  for _, mark in ipairs(global_marks) do
    if mark.file == file and mark.line == line then
      local current_name = mark.name or ""
      local name = vim.fn.input({
        prompt = "Enter mark name: ",
        default = current_name,
      })
      if name ~= "" then
        -- Mark the old key as deleted to prevent duplicates
        local old_key = mark.name or (mark.file .. ":" .. mark.line)
        deleted_marks[old_key] = true

        mark.name = name
        save_marks() -- Save marks immediately
        print("Mark at " .. file .. ":" .. line .. " named '" .. name .. "'")
      else
        print("Mark name not changed.")
      end
      return
    end
  end
  print("No mark found on this line!")
end

local function display_mark(name, file, path)
  local icon, hl_group, icon_width = TSC.get_icon(file)

  local displayer = TSC.make_displayer {
    separator = " ",
    items = {
      { width = icon_width },
      { width = #name },
      { width = 1 },
      { width = #file },
      { width = 1 },
      { width = #path },
    },
  }

  return displayer {
    { icon, hl_group },
    { name, Find.HL_NAMED_BUFFER },
    { ' ' },
    { file, Find.HL_GREY },
    { ' ' },
    { path, Find.HL_COMMENT },
  }
end

local function list_marks(all_marks)
  if #global_marks == 0 then
    print("No marks set!")
    return
  end

  local project_root = vim.fn.getcwd() -- Get the current working directory (project root)
  local mark_list = {}
  for _, mark in ipairs(global_marks) do
    if (all_marks or vim.startswith(mark.file, project_root)) and vim.fn.filereadable(mark.file) == 1 then
      -- Check if showing all marks or if mark is within project root, and file exists
      local file, dir = Find.split_path(mark.file)
      local mark_name = mark.name or string.format("%s:%d", vim.fn.fnamemodify(mark.file, ":t"), mark.line)
      local ordinal = mark_name .. ' ' .. file .. ' ' .. dir

      table.insert(mark_list, {
        -- display = function() display_mark(display_name, file, dir) end,
        display = function() return display_mark(mark_name, file, dir) end,
        value = mark,
        ordinal = ordinal,
      })
    end
  end

  if #mark_list == 0 then
    print(all_marks and "No marks set!" or "No marks set in the current project!")
    return
  end

  local title = "Marks"
  if all_marks then
    title = "All Marks"
  end

  TSC.make_picker({}, Find.vertical_layout(title, {
    finder = TSC.make_table {
      results = mark_list,
      entry_maker = function(entry)
        return {
          value = entry.value,
          display = entry.display,
          ordinal = entry.ordinal,
        }
      end
    },
    previewer = marks_previewer,
    sorter = TSC.make_sorter({}),
    attach_mappings = function(prompt_bufnr)
      actions.select_default:replace(function()
        actions.close(prompt_bufnr)
        local selection = TSC.get_selected_entry()
        if selection then
          vim.cmd("edit " .. selection.value.file)
          vim.fn.cursor(selection.value.line, 0)
          print("Jumped to " .. selection.value.file .. ":" .. selection.value.line)
        end
      end)
      return true
    end,
  })):find()
end

local function place_marks()
  for _, mark in ipairs(global_marks) do
    if vim.fn.bufexists(mark.file) == 1 then
      vim.fn.sign_place(0, '', 'MarkSign', mark.file, { lnum = mark.line, priority = 10 })
    else
      -- print("Warning: Buffer does not exist for file " .. mark.file)
    end
  end
end

local function open_mark_file()
    vim.cmd('edit ' .. marks_file) 
end

-- display a red "m" where the mark is
vim.fn.sign_define("MarkSign", { text = "m", texthl = "Error", numhl = "" })

load_marks() -- Ensure marks are loaded when the module is required

return {
  save_marks = save_marks,
  load_marks = load_marks,
  toggle_mark = toggle_mark,
  name_mark = name_mark,
  list_marks = function() list_marks(false) end,
  list_all_marks = function() list_marks(true) end,
  on_buf_read = place_marks,
  open_mark_file = open_mark_file,

  global_marks = global_marks,
}

