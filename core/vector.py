"""
向量语义检索模块（优雅降级）。

- 若本机已安装 sentence-transformers 且模型可用，则启用中文语义向量检索；
- 否则 available=False，检索自动回退到 LIKE 关键词检索，绝不报错阻塞。

模型为真·神经网络 embedding（如 BAAI/bge-small-zh-v1.5），需在本机执行
install_models.bat 下载一次（约 130MB）。未下载前系统仍可正常使用关键词检索。
"""
import os
import numpy as np


class Embedder:
    def __init__(self, model_name="BAAI/bge-small-zh-v1.5", cache_dir=None):
        self.model_name = model_name
        self.cache_dir = cache_dir or os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "models"
        )
        self.model = None
        self.available = False
        self.dim = 0
        self._loading = False

    def _find_local_snapshot(self):
        """在 cache_dir 里找本地下载好的模型 snapshot 目录。"""
        try:
            from huggingface_hub import scan_cache_dir
            cache_info = scan_cache_dir(self.cache_dir)
            for repo in cache_info.repos:
                if repo.repo_id == self.model_name:
                    for rev in repo.revisions:
                        if rev.snapshot_path and os.path.isdir(rev.snapshot_path):
                            return rev.snapshot_path
        except Exception:
            pass
        # fallback: 直接拼路径
        parts = self.model_name.replace("/", "--").replace("\\", "--")
        snapshot_base = os.path.join(self.cache_dir, f"models--{parts}", "snapshots")
        if os.path.isdir(snapshot_base):
            for name in os.listdir(snapshot_base):
                p = os.path.join(snapshot_base, name)
                if os.path.isdir(p):
                    return p
        return None

    def load(self):
        """加载模型（耗时可放到后台线程）。重复调用安全；成功/失败后返回 available。"""
        if self.available or self._loading:
            return self.available
        self._loading = True
        try:
            from sentence_transformers import SentenceTransformer

            os.makedirs(self.cache_dir, exist_ok=True)

            # 优先离线加载本地缓存，避免每次启动都去连 huggingface.co
            local_path = self._find_local_snapshot()
            if local_path:
                self.model = SentenceTransformer(str(local_path), local_files_only=True)
            else:
                # 本地没有才联网，并缩短超时/重试，避免卡住
                os.environ["HF_HUB_DOWNLOAD_TIMEOUT"] = "15"
                os.environ["HF_HUB_ETAG_TIMEOUT"] = "10"
                os.environ["HF_HUB_MAX_RETRIES"] = "2"
                self.model = SentenceTransformer(
                    self.model_name, cache_folder=self.cache_dir, local_files_only=False
                )
            try:
                self.dim = self.model.get_embedding_dimension()
            except Exception:
                self.dim = self.model.get_sentence_embedding_dimension()
            self.available = True
        except Exception:
            self.available = False
            self.model = None
        finally:
            self._loading = False
        return self.available

    def encode(self, texts):
        """输入文本列表，返回归一化向量矩阵 (n, dim)；不可用或空输入返回 None。"""
        if not self.available or not texts:
            return None
        try:
            emb = self.model.encode(
                list(texts), normalize_embeddings=True, show_progress_bar=False
            )
            return np.asarray(emb, dtype=np.float32)
        except Exception:
            return None

    def encode_query(self, q):
        if not self.available or not q:
            return None
        try:
            emb = self.model.encode([q], normalize_embeddings=True, show_progress_bar=False)
            return np.asarray(emb[0], dtype=np.float32)
        except Exception:
            return None
