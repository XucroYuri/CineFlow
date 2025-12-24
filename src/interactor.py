from typing import List, Optional, Literal
from collections import Counter
import re
from rich.console import Console
from rich.prompt import Prompt, Confirm
from rich.table import Table
from rich.panel import Panel
from .models import GenerationTask

console = Console()

def show_task_summary(tasks: List[GenerationTask], input_dir: str):
    """
    显示任务扫描结果摘要表格
    """
    unique_files = len(set(t.source_file for t in tasks))
    total_segments = len(set(f"{t.source_file}_{t.segment.segment_index}" for t in tasks))
    total_duration = sum(t.segment.duration_seconds for t in tasks)
    estimated_cost = total_duration * 0.005
    
    # Count resolutions
    res_stats = {"horizontal": 0, "vertical": 0}
    for t in tasks:
        res_stats[t.segment.resolution] += 1
    res_str = f"H:{res_stats['horizontal']} / V:{res_stats['vertical']}"
    
    table = Table(title="任务扫描概览 (Scan Summary)", show_header=True, header_style="bold magenta")
    table.add_column("项目 (Item)", style="cyan")
    table.add_column("数值 (Value)", style="green")
    
    table.add_row("输入目录 (Source)", str(input_dir))
    table.add_row("文件数量 (Files)", str(unique_files))
    table.add_row("分镜总数 (Segments)", str(total_segments))
    table.add_row("生成任务 (Total Tasks)", f"{len(tasks)} (含重复变体)")
    table.add_row("分辨率分布 (Resolution)", res_str)
    table.add_row("预计总时长 (Duration)", f"{total_duration} 秒")
    table.add_row("预估成本 (Est. Cost)", f"${estimated_cost:.2f}")
    
    console.print(table)

def interactive_resolution_override(tasks: List[GenerationTask]):
    """
    允许用户强制覆盖所有任务的分辨率
    """
    console.print(Panel("📺 分辨率检查 (Resolution Check)", style="cyan"))
    
    # Check if mixed
    res_types = set(t.segment.resolution for t in tasks)
    is_mixed = len(res_types) > 1
    
    if is_mixed:
        console.print("[yellow]⚠ 检测到任务列表中包含混合分辨率 (横屏/竖屏)。[/yellow]")
    else:
        current = list(res_types)[0]
        console.print(f"当前所有任务分辨率统一为: [bold green]{current}[/bold green]")
        
    console.print("您希望统一修改本批次的分辨率吗?")
    console.print("  [0] 保持原样 (Keep Original)")
    console.print("  [1] 统一为横屏 (Horizontal 16:9)")
    console.print("  [2] 统一为竖屏 (Vertical 9:16)")
    
    choice = Prompt.ask("请选择", choices=["0", "1", "2"], default="0")
    
    if choice == "0":
        return
        
    target_res: Literal["horizontal", "vertical"] = "horizontal" if choice == "1" else "vertical"
    
    count = 0
    for t in tasks:
        if t.segment.resolution != target_res:
            t.segment.resolution = target_res
            count += 1
            
    if count > 0:
        console.print(f"[green]已将 {count} 个任务的分辨率更新为 {target_res}。[/green]")
    else:
        console.print("[dim]无需更新，所有任务已匹配目标分辨率。[/dim]")

def interactive_asset_injection(tasks: List[GenerationTask]):
    """
    Interactive workflow to inject Character IDs.
    Scans ONLY explicit names defined in JSON asset.characters.
    Handles existing IDs by allowing overwrite or skip.
    """
    console.print(Panel("🕵️  角色 ID 注入检查 (Character ID Injection)", style="cyan"))
    
    console.print("此步骤将扫描 JSON 中已定义的角色名称，并辅助您补充或修正官方 ID。")
    if not Confirm.ask("是否开始扫描并修正?", default=True):
        return

    # --- Phase 1: Scan & Analyze ---
    with console.status("[bold green]正在分析 JSON 资产...[/bold green]"):
        file_char_map = {}  # {file_name: Counter(char_name: count)}
        global_char_stats = {} # {char_name: {'files': set(), 'count': 0, 'existing_ids': set()}}

        for task in tasks:
            f_name = task.source_file.name
            if f_name not in file_char_map:
                file_char_map[f_name] = Counter()
            
            for char_str in task.segment.asset.characters:
                # Robust parsing of "Name", "Name@ID", "Name (@ID )"
                name, found_id = _parse_name_and_id(char_str)
                
                if name:
                    file_char_map[f_name][name] += 1
                    
                    if name not in global_char_stats:
                        global_char_stats[name] = {'files': set(), 'count': 0, 'existing_ids': set()}
                    
                    global_char_stats[name]['files'].add(f_name)
                    global_char_stats[name]['count'] += 1
                    if found_id:
                        global_char_stats[name]['existing_ids'].add(found_id)

    if not global_char_stats:
        console.print("[yellow]未在 JSON 文件的 Asset -> Characters 中找到任何角色定义。[/yellow]")
        return

    # --- Phase 2: Report ---
    console.print("\n[bold]📄 待处理角色列表 (Characters from JSON):[/bold]")
    for f_name, counter in file_char_map.items():
        if not counter:
            continue
        chars_list = [f"{k}" for k, v in counter.items()]
        console.print(f" • [cyan]{f_name}[/cyan]: {', '.join(chars_list)}")

    # --- Phase 3: Interactive Injection ---
    sorted_candidates = sorted(global_char_stats.items(), key=lambda x: x[1]['count'], reverse=True)
    
    console.print("\n[bold]🚀 开始 ID 补充流程[/bold]")
    console.print("操作指南: 输入新 ID 回车覆盖。直接 [bold]回车[/bold] 则保持当前状态(跳过)。输入 'q' 结束。")
    
    for name, stats in sorted_candidates:
        existing_ids = stats['existing_ids']
        existing_str = ", ".join(existing_ids) if existing_ids else "[dim]无[/dim]"
        status_color = "green" if existing_ids else "yellow"
        
        console.print(f"\n角色名称: [bold white]{name}[/bold white] (涉及 {stats['count']} 个分镜)")
        console.print(f"[dim]所在文件: {', '.join(list(stats['files'])[:3])}{'...' if len(stats['files'])>3 else ''}[/dim]")
        console.print(f"当前 ID: [{status_color}]{existing_str}[/{status_color}]")
        
        prompt_text = f"请输入 '{name}' 的新 ID" if existing_ids else f"请输入 '{name}' 的 ID"
        char_id = Prompt.ask(prompt_text, default="")
        
        if char_id.lower() == 'q':
            break
            
        if char_id.strip():
            # User provided an ID, apply injection/replacement
            clean_id = char_id.strip()
            _apply_id_injection(tasks, name, clean_id)
        else:
            console.print("[dim]⏭ 保持原状 (跳过)[/dim]")

    console.print("[dim]角色 ID 注入完成。[/dim]\n")

def _parse_name_and_id(char_str: str):
    """
    Extracts name and ID from various formats:
    - "Alice" -> ("Alice", None)
    - "Alice@123" -> ("Alice", "123")
    - "Alice (@123 )" -> ("Alice", "123")
    """
    if '@' not in char_str:
        return char_str.strip(), None
    
    # Split by first @
    # But wait, "Name (@ID)" split '@' gives "Name (" and "ID)"
    # "Name@ID" split '@' gives "Name" and "ID"
    
    # Try regex for the cleaner "Name (@ID)" pattern first
    match_paren = re.search(r'^(.*?)\s*\(@([^)]+)\)\s*$', char_str)
    if match_paren:
        name = match_paren.group(1).strip()
        raw_id = match_paren.group(2).strip()
        # raw_id might be "123 " or "123"
        return name, raw_id
    
    # Fallback to simple split for "Name@ID"
    parts = char_str.split('@')
    name = parts[0].strip()
    raw_id = parts[1].strip()
    return name, raw_id

def _apply_id_injection(tasks: List[GenerationTask], name: str, char_id: str):
    """
    Helper to apply ID injection. 
    1. Updates Prompt to: Name (@ID )
    2. Updates Asset to: Name@ID (Standardized)
    """
    # Prompt format: Name (@ID ) with trailing space for safety
    prompt_id_suffix = f" (@{char_id} )"
    # Asset format: Name@ID (also adding space just in case, per user request for general foolproofing)
    asset_id_str = f"{name}@{char_id} " 
    
    replaced_count = 0
    
    for t in tasks:
        # 1. Update Prompt Text
        if name in t.segment.prompt_text:
            # We need to replace any existing ID format for this name
            # Pattern: Name followed optionally by (@...) or nothing
            # Actually, standard replacement:
            # Find "Name" that is NOT part of an existing correct tag? 
            # Or just replace occurrences.
            
            # Simple approach: Replace "Name" + any old tag -> "Name" + new tag
            # Old tag patterns: " (@old )", "(@old)", etc.
            
            # Regex to find: Name followed by optional existing tag
            # existing tag = \s*\(@[^)]+\)
            pattern = fr"{re.escape(name)}(\s*\(@[^)]+\))?"
            
            # Replacement
            new_prompt = re.sub(pattern, f"{name}{prompt_id_suffix}", t.segment.prompt_text)
            
            if new_prompt != t.segment.prompt_text:
                t.segment.prompt_text = new_prompt
                replaced_count += 1
                
        # 2. Update Asset metadata
        # We need to find the entry for 'name' in the list and update it
        new_char_list = []
        updated_asset = False
        for c in t.segment.asset.characters:
            c_name, _ = _parse_name_and_id(c)
            if c_name == name:
                new_char_list.append(asset_id_str)
                updated_asset = True
            else:
                new_char_list.append(c)
        
        if updated_asset:
            t.segment.asset.characters = new_char_list

    if replaced_count > 0:
        console.print(f" -> [green]已更新 {replaced_count} 处 Prompt (ID: {char_id})。[/green]")
    else:
        # If we didn't update prompt (maybe name not in text), but we updated asset list
        console.print(f" -> [green]已更新关联资产定义 (ID: {char_id})。[/green]")
