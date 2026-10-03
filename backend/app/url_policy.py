import ipaddress
import socket
from urllib.parse import urlsplit

ENTRY_HOSTS = frozenset(
    {
        "youtube.com",
        "www.youtube.com",
        "m.youtube.com",
        "youtu.be",
        "bilibili.com",
        "www.bilibili.com",
        "m.bilibili.com",
        "b23.tv",
    }
)


class UnsafeURL(ValueError):
    pass


def validate_url(url: str, *, entry: bool = False) -> tuple[str, int]:
    if not url or len(url) > 8192 or any(ord(char) <= 32 or ord(char) == 127 for char in url):
        raise UnsafeURL("網址含有不允許的字元。")
    try:
        parsed = urlsplit(url)
        host = parsed.hostname
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
    except ValueError as error:
        raise UnsafeURL("網址格式不正確。") from error
    if (
        parsed.scheme not in {"http", "https"}
        or not host
        or parsed.username is not None
        or parsed.password is not None
        or port != (443 if parsed.scheme == "https" else 80)
        or "\\" in url
        or "%" in host
    ):
        raise UnsafeURL("請使用沒有帳密的標準 HTTP(S) 影片網址。")
    if entry and host not in ENTRY_HOSTS:
        raise UnsafeURL("目前支援 YouTube 與 Bilibili 的影片連結。")
    return host, port


def require_public_ip(value: str) -> None:
    try:
        address = ipaddress.ip_address(value.split("%", 1)[0])
    except ValueError as error:
        raise UnsafeURL("連線目的地必須是 IP。") from error
    mapped = getattr(address, "ipv4_mapped", None)
    if not address.is_global or (mapped is not None and not mapped.is_global):
        raise UnsafeURL("不允許存取本機、內網或保留位址。")


def resolve_public(host: str, port: int, resolver=socket.getaddrinfo):
    records = resolver(host, port, type=socket.SOCK_STREAM)
    if not records:
        raise UnsafeURL("無法解析連線目的地。")
    for record in records:
        require_public_ip(record[4][0])
    return records


def install_socket_guard() -> None:
    """僅在隔離 worker 安裝：驗證實際 sockaddr，避免檢查後再次解析。"""
    original_socket = socket.socket
    original_resolver = socket.getaddrinfo

    class PublicSocket(original_socket):
        def connect(self, address):
            if self.family not in {socket.AF_INET, socket.AF_INET6}:
                raise UnsafeURL("不允許非 IP 連線。")
            host, port = address[:2]
            if port not in {80, 443}:
                raise UnsafeURL("不允許非標準連接埠。")
            try:
                ipaddress.ip_address(host)
                target = address
            except ValueError:
                target = resolve_public(host, port, original_resolver)[0][4]
            require_public_ip(target[0])
            return super().connect(target)

        def connect_ex(self, address):
            try:
                self.connect(address)
                return 0
            except OSError as error:
                return error.errno or 1

    socket.socket = PublicSocket
