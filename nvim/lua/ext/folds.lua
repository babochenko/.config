local M = {}

-- z-prefix builtins to strip from both the keyboard and the which-key popup.
-- Shared with plugins.lua, which feeds M.is_disabled to which-key's filter:
-- setting plugins.presets.z = false only drops which-key's own z descriptions,
-- so zf ("Create fold", from the operators preset) and z= (from the spelling
-- plugin) still surface. Filtering on lhs catches every source at once.
M.disabled = {
    'z<CR>', 'z=', 'zA', 'zC', 'zD', 'zE', 'zH', 'zL', 'zM', 'zO', 'zR', 'zb',
    'zc', 'zd', 'ze', 'zf', 'zg', 'zi', 'zm', 'zo', 'zr', 'zt', 'zv', 'zw',
    'zx', 'zz',
}

local function norm(lhs)
    return vim.api.nvim_replace_termcodes(lhs, true, true, true)
end

local lookup = {}
for _, key in ipairs(M.disabled) do
    lookup[norm(key)] = true
end

-- which-key hands us raw lhs, so z<CR> arrives as "z\r"
function M.is_disabled(lhs)
    return lhs ~= nil and lookup[norm(lhs)] == true
end

function M.toggle_all()
    -- zM parks foldlevel at 0 and zR raises it, so foldlevel is the whole state
    vim.cmd(vim.wo.foldlevel == 0 and 'normal! zR' or 'normal! zM')
end

return M
