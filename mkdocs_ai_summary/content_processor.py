"""内容处理器模块

负责处理页面内容、判断是否生成摘要、格式化摘要显示等功能。
"""

import re
import hashlib
import fnmatch
import yaml
from typing import List, Optional
from mkdocs.structure.pages import Page


class ContentProcessor:
    """内容处理器"""
    
    def __init__(self, enabled_folders: List[str], exclude_patterns: List[str],
                 exclude_files: List[str], summary_language: str, debug: bool = False,
                 default_enabled_folders: List[str] = None, default_exclude_patterns: List[str] = None,
                 max_content_length: int = 2000, docs_dir: str = 'docs'):
        """初始化内容处理器

        Args:
            enabled_folders: 启用摘要的文件夹列表
            exclude_patterns: 排除模式列表
            exclude_files: 排除文件列表
            summary_language: 摘要语言
            debug: 是否启用调试模式
            default_enabled_folders: 默认启用文件夹列表
            default_exclude_patterns: 默认排除模式列表
            max_content_length: AI处理的最大内容长度
            docs_dir: 文档目录路径
        """
        # 首先设置基本属性
        self.exclude_files = exclude_files
        self.summary_language = summary_language
        self.debug = debug
        self.max_content_length = max_content_length
        self.docs_dir = docs_dir

        # 设置默认值
        self.default_enabled_folders = default_enabled_folders or ['']
        self.default_exclude_patterns = default_exclude_patterns or ['tag.md']

        # 应用优先级逻辑：用户配置覆盖默认配置
        raw_enabled_folders = self._apply_user_config_priority(
            enabled_folders, self.default_enabled_folders
        )
        self.enabled_folders = self._normalize_enabled_folders(raw_enabled_folders)
        self.exclude_patterns = self._apply_user_config_priority(
            exclude_patterns, self.default_exclude_patterns
        )
        
        if self.debug:
            # 显示配置信息
            if raw_enabled_folders:
                print(f"📁 启用文件夹 (用户配置): {self.enabled_folders}")
            else:
                print(f"📁 启用文件夹 (自动发现): {self.enabled_folders}")

            if self.exclude_patterns == self.default_exclude_patterns:
                print(f"🚫 排除模式 (默认): {self.exclude_patterns}")
            else:
                print(f"🚫 排除模式 (用户配置): {self.exclude_patterns}")
            print()  # 添加空行分隔
    
    def _apply_user_config_priority(self, user_config: List[str], default_config: List[str]) -> List[str]:
        """应用用户配置优先级逻辑

        Args:
            user_config: 用户配置的列表
            default_config: 默认配置的列表

        Returns:
            List[str]: 最终使用的配置列表
        """
        # 如果用户明确配置了非空列表，则完全使用用户配置
        if user_config:
            return user_config
        # 只有当用户配置为空列表或未配置时，才使用默认配置
        return default_config

    def _normalize_enabled_folders(self, folders: List[str]) -> List[str]:
        """标准化enabled_folders路径，统一为相对于docs_dir的路径

        Args:
            folders: 原始enabled_folders列表（可能是docs_dir名称、绝对路径、或相对路径）

        Returns:
            List[str]: 标准化后的路径列表
        """
        docs_dir_norm = self.docs_dir.replace('\\', '/').rstrip('/')
        docs_prefix = docs_dir_norm + '/'
        docs_name = docs_dir_norm.split('/')[-1]  # 纯粹的docs目录名

        normalized = []
        for folder in folders:
            f = folder.replace('\\', '/').rstrip('/')
            if not f:
                normalized.append('')
                continue
            # 路径以完整docs_dir开头，去掉前缀
            if f == docs_dir_norm or f.startswith(docs_prefix):
                f = f[len(docs_prefix):] if f != docs_dir_norm else ''
            # 路径以docs目录名开头（如 docs/计算机/...）
            elif f == docs_name:
                f = ''
            elif f.startswith(docs_name + '/'):
                f = f[len(docs_name) + 1:]
            normalized.append(f)
        return normalized
    
    def should_generate_summary(self, page: Page) -> bool:
        """判断是否应该为页面生成摘要
        
        Args:
            page: MkDocs页面对象
            
        Returns:
            bool: True表示应该生成摘要，False表示不应该生成
        """
        file_path = str(page.file.src_path)
        
        # 检查排除文件
        if file_path in self.exclude_files:
            return False
        
        # 检查排除模式
        for pattern in self.exclude_patterns:
            if pattern in file_path or fnmatch.fnmatch(file_path, pattern):
                return False
        
        # 检查启用文件夹
        for folder in self.enabled_folders:
            if folder == '' or file_path.startswith(folder):
                return True

        return False
    
    def parse_front_matter(self, markdown: str) -> tuple[Optional[dict], str]:
        """解析markdown的front matter
        
        Args:
            markdown: 原始markdown内容
            
        Returns:
            tuple: (front_matter_dict, content_without_front_matter)
        """
        # 更灵活的正则表达式，支持多种front matter格式
        front_matter_patterns = [
            r'^---\s*\n(.*?)\n---\s*\n',  # 标准格式：--- 后有换行
            r'^---\s*\n(.*?)\n---\s*$',   # 结尾没有换行
            r'^---\s*\n(.*?)\n---',       # 最简格式
        ]
        
        for pattern in front_matter_patterns:
            front_matter_match = re.match(pattern, markdown, re.DOTALL | re.MULTILINE)
            if front_matter_match:
                try:
                    front_matter_yaml = front_matter_match.group(1)
                    front_matter = yaml.safe_load(front_matter_yaml)
                    content = markdown[front_matter_match.end():]
                    
                    # 调试日志
                    if hasattr(self, 'debug') and self.debug:
                        if 'ai_summary_lang' in front_matter:
                            print(f"🌐 页面语言: {front_matter['ai_summary_lang']}")
                    
                    return front_matter, content
                except yaml.YAMLError as e:
                    # 调试日志
                    if hasattr(self, 'debug') and self.debug:
                        print(f"⚠️ YAML解析失败: {str(e)[:50]}...")
                    continue
        
        # 调试日志（简化）
        # if hasattr(self, 'debug') and self.debug:
        #     print(f"[DEBUG] No front matter found")
        
        return None, markdown
    
    def get_page_language(self, page) -> str:
        """获取页面级别的语言设置
        
        Args:
            page: MkDocs页面对象
            
        Returns:
            str: 页面语言设置，如果没有设置则返回全局设置
        """
        # 从 MkDocs Page 对象的 meta 属性获取 Front Matter
        page_meta = getattr(page, 'meta', {})
        
        # 简化调试日志
        if self.debug and page_meta:
            if 'ai_summary_lang' in page_meta:
                print(f"🌐 页面语言: {page_meta['ai_summary_lang']}")
            else:
                print(f"📝 使用全局语言: {self.summary_language}")
        
        if page_meta and 'ai_summary_lang' in page_meta:
            page_lang = page_meta['ai_summary_lang']
            
            # 验证语言设置是否有效
            if page_lang in ['zh', 'en', 'both']:
                return page_lang
            else:
                if self.debug:
                    print(f"⚠️ 无效语言设置 '{page_lang}'，使用全局设置")
        
        return self.summary_language
    
    def clean_content_for_ai(self, markdown: str) -> str:
        """清理内容用于AI处理
        
        Args:
            markdown: 原始markdown内容
            
        Returns:
            str: 清理后的内容
        """
        content = markdown
        
        # 移除YAML front matter
        content = re.sub(r'^---.*?---\s*', '', content, flags=re.DOTALL)
        
        # 移除已存在的摘要块
        content = re.sub(r'!!! info "📖 阅读信息".*?(?=\n\n|\n#|\Z)', '', content, flags=re.DOTALL)
        content = re.sub(r'!!! abstract "🤖 AI摘要".*?(?=\n\n|\n#|\Z)', '', content, flags=re.DOTALL)
        
        # 移除代码块
        content = re.sub(r'```.*?```', '', content, flags=re.DOTALL)
        content = re.sub(r'`[^`]+`', '', content)
        
        # 移除图片和链接
        content = re.sub(r'!\[.*?\]\(.*?\)', '', content)
        content = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', content)
        
        # 移除HTML标签
        content = re.sub(r'<[^>]+>', '', content)
        
        # 清理多余空白
        content = re.sub(r'\n\s*\n', '\n\n', content)
        content = content.strip()
        
        return content
    
    def get_content_hash(self, file_path: str, content: str, language: Optional[str] = None) -> str:
        """生成内容哈希
        
        Args:
            file_path: 文件路径
            content: 文件内容（保留参数兼容性，但不用于哈希生成）
            language: 语言设置，如果为None则使用默认语言
            
        Returns:
            str: MD5哈希值（基于文件路径+语言，确保同一文件对应固定缓存）
        """
        lang = language or self.summary_language
        # 只基于文件路径和语言生成哈希，确保同一文件始终对应同一个缓存文件
        # 当内容变化时，会覆盖原有缓存而不是创建新文件
        combined_key = f"{file_path}_{lang}"
        return hashlib.md5(combined_key.encode('utf-8')).hexdigest()
    
    def format_summary(self, summary: str, service: str, language: str) -> str:
        """格式化摘要显示
        
        Args:
            summary: 摘要内容
            service: AI服务名称
            language: 摘要语言
            
        Returns:
            str: 格式化后的摘要markdown
        """
        # 服务图标映射
        service_icons = {
            'deepseek': '🧠',
            'openai': '🤖',
            'gemini': '✨',
            'glm': '⚡',
            'siliconflow': '💡',
            'qwen': '💡',
            'fallback': '📝'
        }

        icon = service_icons.get(service.lower(), '💡')

        if language == 'zh':
            title = f"{icon} AI摘要 ({service.upper()})"
        else:
            title = f"{icon} AI Summary ({service.upper()})"

        indented = '\n'.join(f'    {line}' for line in summary.split('\n'))
        return f'!!! abstract "{title}"\n{indented}\n'
    
    def inject_summary(self, markdown: str, summary: str) -> str:
        """将摘要注入到markdown内容中
        
        Args:
            markdown: 原始markdown内容
            summary: 格式化后的摘要
            
        Returns:
            str: 注入摘要后的markdown内容
        """
        # 移除YAML front matter以找到正确的插入位置
        front_matter_match = re.match(r'^(---.*?---\s*)', markdown, re.DOTALL)
        
        if front_matter_match:
            front_matter = front_matter_match.group(1)
            content = markdown[len(front_matter):]
        else:
            front_matter = ''
            content = markdown
        
        # 查找第一个h1标题（以 # 开头的行）
        lines = content.split('\n')
        h1_index = -1
        
        for i, line in enumerate(lines):
            # 匹配以 # 开头的行（h1标题），但不匹配 ## 或更多#
            if re.match(r'^#\s+', line.strip()):
                h1_index = i
                break
        
        if h1_index >= 0:
            # 在h1标题后插入摘要
            lines.insert(h1_index + 1, '')
            lines.insert(h1_index + 2, summary.rstrip())
            lines.insert(h1_index + 3, '')
            modified_content = '\n'.join(lines)
        else:
            # 如果没有找到h1标题，则插入到内容开头
            # 确保摘要和原内容之间有适当的空行分隔
            if content.strip():
                # 如果原内容开头已有空行，保持原有格式
                if content.startswith('\n'):
                    modified_content = summary.rstrip() + '\n' + content
                else:
                    # 在摘要和内容之间添加空行
                    modified_content = summary.rstrip() + '\n\n' + content
            else:
                # 如果没有内容，只添加摘要
                modified_content = summary.rstrip() + '\n'
        
        return front_matter + modified_content
    
    def get_fallback_summary(self, title: str, language: str = 'zh') -> str:
        """生成备用摘要
        
        Args:
            title: 页面标题
            language: 摘要语言
            
        Returns:
            str: 备用摘要内容
        """
        if language == 'zh':
            return f"本文档《{title}》包含重要内容，建议仔细阅读以获取详细信息。"
        else:
            return f"This document '{title}' contains important content. Please read carefully for detailed information."
    
    def validate_summary_content(self, summary: str) -> bool:
        """验证摘要内容
        
        Args:
            summary: 摘要内容
            
        Returns:
            bool: True表示摘要有效，False表示无效
        """
        if not summary or not summary.strip():
            return False
        
        # 检查摘要长度（至少10个字符）
        if len(summary.strip()) < 10:
            return False
        
        # 检查是否包含明显的错误信息
        error_indicators = ['error', 'failed', 'unable', '错误', '失败', '无法']
        summary_lower = summary.lower()
        
        for indicator in error_indicators:
            if indicator in summary_lower:
                return False
        
        return True
    
    def truncate_content(self, content: str, max_length: int = None) -> str:
        """截断内容到指定长度

        Args:
            content: 原始内容
            max_length: 最大长度，默认使用配置的max_content_length

        Returns:
            str: 截断后的内容
        """
        if max_length is None:
            max_length = self.max_content_length

        if len(content) <= max_length:
            return content

        # 尝试在句号处截断
        truncated = content[:max_length]
        last_period = truncated.rfind('。')
        if last_period > max_length * 0.8:  # 如果句号位置合理
            return truncated[:last_period + 1]

        # 否则直接截断并添加省略号
        return truncated + '...'