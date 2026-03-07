#!/usr/bin/env bash
set -e

workspace_dir="$(pwd)"

append_if_missing() {
	local line="$1"
	local file="$2"
	touch "$file"
	grep -qxF "$line" "$file" || echo "$line" >> "$file"
}

mkdir -p ~/.config
ln -sf "${workspace_dir}/.devcontainer/starship.toml" ~/.config/starship.toml
git config --global --get-all safe.directory | grep -qxF "${workspace_dir}" || git config --global --add safe.directory "${workspace_dir}"
git config --global user.name "Virgil"
git config --global user.email "Virgil@example.com"
append_if_missing 'eval "$(starship init zsh)"' ~/.zshrc

# Zsh autocomplete plugins
zsh_base="${ZSH:-$HOME/.oh-my-zsh}"
custom_dir="${ZSH_CUSTOM:-$zsh_base/custom}"
if [ "$custom_dir" = "$zsh_base" ]; then
	custom_dir="$zsh_base/custom"
fi

plugin_dir="$custom_dir/plugins"
mkdir -p "$plugin_dir"

misplaced_dir="$zsh_base/plugins"
if [ -d "$misplaced_dir" ] && [ "$misplaced_dir" != "$plugin_dir" ]; then
	if [ -d "$misplaced_dir/zsh-autosuggestions" ] && [ ! -d "$plugin_dir/zsh-autosuggestions" ]; then
		mv "$misplaced_dir/zsh-autosuggestions" "$plugin_dir/"
	fi

	if [ -d "$misplaced_dir/zsh-completions" ] && [ ! -d "$plugin_dir/zsh-completions" ]; then
		mv "$misplaced_dir/zsh-completions" "$plugin_dir/"
	fi
fi

if [ ! -d "${plugin_dir}/zsh-autosuggestions/.git" ]; then
	git clone https://github.com/zsh-users/zsh-autosuggestions "${plugin_dir}/zsh-autosuggestions"
fi

if [ ! -d "${plugin_dir}/zsh-completions/.git" ]; then
	git clone https://github.com/zsh-users/zsh-completions "${plugin_dir}/zsh-completions"
fi

if ! grep -qxF 'plugins=(git zsh-autosuggestions zsh-completions)' ~/.zshrc; then
	sed -i 's/^plugins=(.*/plugins=(git zsh-autosuggestions zsh-completions)/' ~/.zshrc
fi

# claude shorthand: p <prompt>
append_if_missing 'p() { claude -p "$*" --model claude-haiku-4-5-20251001 --output-format text; }' ~/.zshrc

# uv
uv pip install -r requirements.txt -r requirements-dev.txt --system --no-deps
