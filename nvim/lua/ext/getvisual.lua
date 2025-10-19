-- returns current visual selection. Used in e.g. mymath.lua
-- for modifying exactly the selected text

local function _lines_objs(l1, l2, lcol, rcol)
  local res = {}
  for row = l1, l2 do
    local line = vim.fn.getline(row)
    line = line:sub(lcol, rcol)
    table.insert(res, {
      text=line,
      line=row,
      lcol=lcol,
      rcol=rcol,
    })
  end
  return res
end

local function _visual_line(l1, lcol, rcol)
  return _lines_objs(l1, l1, lcol, rcol)
end

local function _visual_block(l1, l2, lcol, rcol)
  return _lines_objs(l1, l2, lcol, rcol)
end

local function _visual_lines(l1, l2, lcol, rcol)
  return _lines_objs(l1, l2, 0, -1)
end

local vis_char = 'v'
local vis_line = 'V'
local vis_block = '\22'

local function _visual()
  local l = vim.fn.getpos("'<")
  local r = vim.fn.getpos("'>")
  local l1, lcol = l[2], l[3]
  local l2, rcol = r[2], r[3]

  if l1 == l2 then
    return _visual_line(l1, lcol, rcol)
  else
    local mode = vim.fn.visualmode()
    if mode == vis_char or mode == vis_line then
      return _visual_lines(l1, l2, lcol, rcol)
    elseif mode == vis_block then
      return _visual_block(l1, l2, lcol, rcol)
    else
      return {}
    end
  end
end

return {
  getvisual = _visual,
  vis_char = vis_char,
  vis_line = vis_line,
  vis_block = vis_block,
}

