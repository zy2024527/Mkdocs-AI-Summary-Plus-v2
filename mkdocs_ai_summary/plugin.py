"""MkDocs AI Summary Plugin 主插件类

这是插件的核心入口，负责协调各个模块的工作。
"""

from typing import List
from mkdocs.config import config_options
from mkdocs.plugins import BasePlugin
from mkdocs.structure.files import File
from mkdocs.structure.pages import Page
from mkdocs.config.defaults import MkDocsConfig

from .ai_services import AIServiceManager
from .cache_manager import CacheManager
from .content_processor import ContentProcessor
from .config_manager import ConfigManager


class AISummaryPlugin(BasePlugin):
    """MkDocs AI Summary Plugin"""
    
    config_scheme = (
        # AI服务配置
        ('ai_service', config_options.Type(str, default='glm')),
        ('fallback_services', config_options.Type(list, default=[])),
        ('custom_services', config_options.Type(dict, default={})),
        ('model', config_options.Type(str, default='glm-4-flash')),
        ('max_tokens', config_options.Type(int, default=3000)),
        ('temperature', config_options.Type(float, default=0.3)),
        
        # 缓存配置
        ('cache_enabled', config_options.Type(bool, default=True)),
        ('cache_expire_days', config_options.Type(int, default=30)),
        ('cache_auto_clean', config_options.Type(bool, default=True)),
        
        # 环境配置
        ('local_enabled', config_options.Type(bool, default=True)),
        ('ci_enabled', config_options.Type(bool, default=True)),
        ('ci_cache_only', config_options.Type(bool, default=False)),
        ('ci_fallback', config_options.Type(bool, default=True)),
        
        # 文件夹和排除规则
        ('enabled_folders', config_options.Type(list, default=[])), # 启用的文件夹（空列表=自动发现）
        ('exclude_patterns', config_options.Type(list, default=['tag.md'])), # 排除标签页
        ('exclude_files', config_options.Type(list, default=['blog/index.md'])), # 排除博客首页
        
        # 语言配置
        ('summary_language', config_options.Choice(['zh', 'en', 'both'], default='zh')),
        
        # 内容处理配置
        ('max_content_length', config_options.Type(int, default=2000)),

        # 调试配置
        ('debug', config_options.Type(bool, default=False)),

        # 缓存清理配置
        ('clear_cache', config_options.Type(bool, default=False)),
    )
    
    def _discover_docs_structure(self, config: MkDocsConfig) -> List[str]:
        """动态发现 docs 文件夹结构

        Args:
            config: MkDocs配置对象

        Returns:
            List[str]: 发现的文件夹路径列表（相对于docs_dir）
        """
        import os

        docs_dir = config.get('docs_dir', 'docs')
        discovered_folders = set()

        if not os.path.exists(docs_dir):
            return ['']

        discovered_folders.add('')

        for root, dirs, files in os.walk(docs_dir):
            rel_root = os.path.relpath(root, docs_dir)
            if rel_root == '.':
                continue

            folder_path = rel_root.replace('\\', '/') + '/'
            discovered_folders.add(folder_path)

            has_md_files = any(file.endswith('.md') for file in files)
            if has_md_files:
                current_folder = rel_root.replace('\\', '/') + '/'
                discovered_folders.add(current_folder)

        result = sorted(list(discovered_folders))

        if not result:
            result = ['']

        return result
    
    def on_config(self, config: MkDocsConfig) -> MkDocsConfig:
        """插件配置初始化
        
        Args:
            config: MkDocs配置对象
            
        Returns:
            MkDocsConfig: 处理后的配置对象
        """
        # 初始化配置管理器
        self.config_manager = ConfigManager(self.config)
        
        # 记录环境状态
        self.config_manager.log_environment_status(debug=self.config['debug'])
        
        # 如果不应该运行，直接返回
        if not self.config_manager.should_run():
            return config
        
        # 初始化缓存管理器
        self.cache_manager = CacheManager(
            enabled=self.config['cache_enabled'],
            expire_days=self.config['cache_expire_days'],
            auto_clean=self.config['cache_auto_clean']
        )
        
        # 检查是否需要清理所有缓存
        if self.config['clear_cache']:
            if self.config['debug']:
                print("🧹 检测到clear_cache=True，正在清理所有缓存...")
            self.cache_manager.clear_all_cache()
        
        # 初始化AI服务管理器
        self.ai_service_manager = AIServiceManager(
            default_service=self.config['ai_service'],
            fallback_services=self.config['fallback_services'],
            custom_services=self.config['custom_services'],
            model=self.config['model'],
            max_tokens=self.config['max_tokens'],
            temperature=self.config['temperature']
        )
        
        # 验证AI服务配置
        if not self.ai_service_manager.validate_service_config(debug=self.config['debug']):
            print("⚠️ AI服务配置验证失败，插件将不会生成摘要")
            self._service_available = False
        else:
            self._service_available = True
        
        # 动态发现 docs 结构作为默认配置
        discovered_docs_structure = self._discover_docs_structure(config)
        
        # 初始化内容处理器
        docs_dir = config.get('docs_dir', 'docs')
        self.content_processor = ContentProcessor(
            enabled_folders=self.config['enabled_folders'],
            exclude_patterns=self.config['exclude_patterns'],
            exclude_files=self.config['exclude_files'],
            summary_language=self.config['summary_language'],
            debug=self.config['debug'],
            default_enabled_folders=discovered_docs_structure,
            default_exclude_patterns=['tag.md'],
            max_content_length=self.config['max_content_length'],
            docs_dir=docs_dir,
        )
        
        # 检查服务配置变更
        if self.cache_manager.enabled:
            from . import __version__
            current_config = {
                'ai_service': self.config['ai_service'],
                'summary_language': self.config['summary_language'],
                'version': __version__
            }
            self.cache_manager.check_service_change(current_config)
        
        return config
    
    def on_page_markdown(self, markdown: str, page: Page, config: MkDocsConfig, files) -> str:
        """处理页面markdown内容，生成AI摘要
        
        Args:
            markdown: 页面的markdown内容
            page: MkDocs页面对象
            config: MkDocs配置对象
            files: 文件列表
            
        Returns:
            str: 处理后的markdown内容
        """
        # 检查是否应该运行插件
        if not hasattr(self, 'config_manager') or not self.config_manager.should_run():
            return markdown
        
        # 检查是否应该为此页面生成摘要
        file_path = str(page.file.src_path)
        should_generate = self.content_processor.should_generate_summary(page)
        
        if not should_generate:
            if self.config['debug']:
                print(f"⏭️ 跳过: {file_path}")
            return markdown
        
        if self.config['debug']:
            page_language = self.content_processor.get_page_language(page)
            print(f"📄 处理: {file_path} → {page.title}")
            print(f"🌐 页面语言: {page_language}")
        
        # 检查AI服务是否可用
        if not self._service_available:
            return markdown
        
        try:
            # 获取页面级别的语言设置（如果之前没有获取）
            if not self.config['debug']:
                page_language = self.content_processor.get_page_language(page)
            
            # 清理内容并生成哈希
            cleaned_content = self.content_processor.clean_content_for_ai(markdown)
            # 生成文件哈希（基于路径+语言，用于缓存文件名）
            file_hash = self.content_processor.get_content_hash(file_path, "", page_language)
            # 生成内容哈希（基于实际内容，用于检测变化）
            import hashlib
            content_hash = hashlib.md5(f"{cleaned_content}_{page_language}".encode('utf-8')).hexdigest()
            
            # 检查内容是否发生变化
            content_changed = self.cache_manager.is_content_changed(file_hash, content_hash)
            
            # 尝试从缓存获取摘要（只有在内容未变化时才使用缓存）
            cached_summary = None
            if not content_changed:
                cached_summary = self.cache_manager.get_cached_summary(file_hash)
            
            if cached_summary and not content_changed:
                summary_text = cached_summary['summary']
                service_used = cached_summary['service']
                if self.config['debug']:
                    print(f"💾 缓存命中 ({service_used})")
            else:
                # 检查是否允许生成新摘要
                if not self.config_manager.should_generate_new_summary():
                    # 如果是CI环境且仅缓存模式，尝试使用备用摘要
                    if self.config_manager.get_fallback_enabled():
                        summary_text = self.content_processor.get_fallback_summary(
                            page.title, page_language
                        )
                        service_used = 'fallback'
                        if self.config['debug']:
                            print(f"📝 备用摘要 ({page_language})")
                    else:
                        return markdown
                else:
                    # 调用AI服务生成摘要
                    if self.config['debug']:
                        print(f"🤖 生成中... ({page_language})")
                    
                    # 截断内容以避免过长
                    truncated_content = self.content_processor.truncate_content(cleaned_content)
                    
                    # AI服务管理器会自动尝试所有可用的服务（包括fallback）
                    summary_result = self.ai_service_manager.generate_summary(
                        truncated_content, page.title, page_language, debug=self.config['debug']
                    )
                    
                    if summary_result and self.content_processor.validate_summary_content(summary_result['summary']):
                        summary_text = summary_result['summary']
                        service_used = summary_result['service']
                        
                        if self.config['debug']:
                            print(f"✅ 生成完成 ({service_used})")
                        
                        # 保存到缓存
                        self.cache_manager.save_summary_cache(file_hash, {
                            'summary': summary_text,
                            'service': service_used,
                            'page_title': page.title
                        }, content_hash)
                    else:
                        # 所有AI服务都失败了，使用备用摘要
                        if self.config_manager.get_fallback_enabled():
                            summary_text = self.content_processor.get_fallback_summary(
                                page.title, page_language
                            )
                            service_used = 'fallback'
                            if self.config['debug']:
                                print(f"⚠️ 所有AI服务失败，使用备用摘要 ({page_language})")
                        else:
                            if self.config['debug']:
                                print(f"❌ 所有AI服务失败，跳过")
                            return markdown
            
            # 格式化并插入摘要
            formatted_summary = self.content_processor.format_summary(
                summary_text, service_used, page_language
            )
            
            return self.content_processor.inject_summary(markdown, formatted_summary)
            
        except Exception as e:
            # 错误处理
            if self.config['debug']:
                print(f"⚠️ 处理异常: {str(e)[:50]}...")
            
            # 如果启用了备用摘要，使用备用摘要
            if self.config_manager.get_fallback_enabled():
                try:
                    # 获取页面语言设置（异常处理中重新获取）
                    page_language = self.content_processor.get_page_language(page)
                    fallback_summary = self.content_processor.get_fallback_summary(
                        page.title, page_language
                    )
                    formatted_summary = self.content_processor.format_summary(
                        fallback_summary, 'fallback', page_language
                    )
                    if self.config['debug']:
                        print(f"📝 异常备用摘要 ({page_language})")
                    return self.content_processor.inject_summary(markdown, formatted_summary)
                except Exception as fallback_error:
                    if self.config['debug']:
                        print(f"⚠️ 备用摘要失败: {str(fallback_error)[:30]}...")
            
            return markdown
    
    def on_post_build(self, config: MkDocsConfig) -> None:
        """构建完成后的清理工作
        
        Args:
            config: MkDocs配置对象
        """
        if hasattr(self, 'config_manager') and self.config_manager.should_run():
            if self.config['debug']:
                # 显示统计信息
                stats = []
                if hasattr(self, 'ai_service_manager'):
                    available_services = self.ai_service_manager.get_available_services()
                    stats.append(f"服务: {', '.join(available_services)}")
                
                if hasattr(self, 'cache_manager') and self.cache_manager.enabled:
                    cache_files = list(self.cache_manager.cache_dir.glob("*.json"))
                    cache_count = len([f for f in cache_files if f.name != "service_config.json"])
                    stats.append(f"缓存: {cache_count}")
                
                print(f"\n🎉 构建完成 | {' | '.join(stats)}")
                print()  # 添加空行分隔