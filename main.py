"""Backend FastAPI untuk Kalkulator Subnet & VLSM IPv4."""

from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

BASE_DIR = Path(__file__).resolve().parent

app = FastAPI(
    title="Kalkulator Subnet & VLSM IPv4",
    description="API perhitungan subnetting IPv4 dan alokasi VLSM sesuai standar RFC 3021.",
    version="1.0.0",
)


def _ip_to_int(ip: str) -> int:
    """Mengonversi string alamat IPv4 menjadi bilangan bulat 32-bit unsigned."""
    if not isinstance(ip, str) or not ip or ip != ip.strip() or " " in ip:
        raise ValueError("Alamat IPv4 tidak boleh kosong atau mengandung spasi.")

    parts = ip.split(".")
    if len(parts) != 4:
        raise ValueError("Alamat IPv4 harus terdiri dari tepat 4 oktet.")

    result = 0
    for part in parts:
        if not part.isdigit():
            raise ValueError(f"Oktet '{part}' harus berupa angka bulat.")
        if len(part) > 1 and part.startswith("0"):
            raise ValueError(f"Oktet '{part}' tidak boleh memiliki angka nol di depan.")
        val = int(part)
        if val < 0 or val > 255:
            raise ValueError(f"Oktet '{part}' harus berada pada rentang 0 sampai 255.")
        result = (result << 8) | val

    return result


def _int_to_ip(val: int) -> str:
    """Mengonversi bilangan bulat 32-bit menjadi format desimal bertitik (a.b.c.d)."""
    return ".".join(
        str((val >> shift) & 0xFF) for shift in (24, 16, 8, 0)
    )


def _prefix_to_mask_int(prefix: int) -> int:
    """Menghitung subnet mask 32-bit dari prefix CIDR (0-32)."""
    if not isinstance(prefix, int) or isinstance(prefix, bool) or prefix < 0 or prefix > 32:
        raise ValueError("Prefix harus berupa bilangan bulat antara 0 sampai 32.")
    if prefix == 0:
        return 0
    return ((0xFFFFFFFF << (32 - prefix)) & 0xFFFFFFFF)


def hitung_subnet(ip: str, prefix: int) -> dict[str, Any]:
    """Menghitung parameter subnet IPv4 berdasarkan alamat IP dan prefix CIDR."""
    ip_int = _ip_to_int(ip)
    mask_int = _prefix_to_mask_int(prefix)

    # Operasi bitwise AND untuk memperoleh alamat network
    network_int = ip_int & mask_int
    mask_str = _int_to_ip(mask_int)
    network_str = _int_to_ip(network_int)

    if prefix == 31:
        # Aturan Point-to-Point RFC 3021
        return {
            "mask": mask_str,
            "network": network_str,
            "broadcast": None,
            "first_host": network_str,
            "last_host": _int_to_ip(network_int + 1),
            "usable_hosts": 2,
        }

    if prefix == 32:
        # Aturan Host Tunggal (/32)
        return {
            "mask": mask_str,
            "network": network_str,
            "broadcast": None,
            "first_host": ip,
            "last_host": ip,
            "usable_hosts": 1,
        }

    wildcard_int = (~mask_int) & 0xFFFFFFFF
    broadcast_int = network_int | wildcard_int
    usable_hosts = (1 << (32 - prefix)) - 2

    return {
        "mask": mask_str,
        "network": network_str,
        "broadcast": _int_to_ip(broadcast_int),
        "first_host": _int_to_ip(network_int + 1),
        "last_host": _int_to_ip(broadcast_int - 1),
        "usable_hosts": usable_hosts,
    }


def alokasi_vlsm(network_cidr: str, kebutuhan_host: list[int]) -> list[dict[str, Any]]:
    """Mengalokasikan blok subnet VLSM secara berurutan dari kebutuhan terbesar."""
    if not isinstance(network_cidr, str) or not network_cidr or network_cidr != network_cidr.strip() or "/" not in network_cidr:
        raise ValueError("Format network_cidr harus berupa '<ip>/<prefix>' tanpa spasi.")

    parts = network_cidr.split("/")
    if len(parts) != 2:
        raise ValueError("Format network_cidr tidak valid.")

    ip_str, prefix_str = parts
    ip_int = _ip_to_int(ip_str)

    if not prefix_str.isdigit() or (len(prefix_str) > 1 and prefix_str.startswith("0")):
        raise ValueError("Prefix CIDR pada network_cidr tidak valid.")

    parent_prefix = int(prefix_str)
    parent_mask = _prefix_to_mask_int(parent_prefix)

    if (ip_int & parent_mask) != ip_int:
        raise ValueError("Alamat IP pada network_cidr bukan merupakan alamat jaringan (network address) yang valid.")

    if not isinstance(kebutuhan_host, list) or len(kebutuhan_host) == 0:
        raise ValueError("Daftar kebutuhan_host tidak boleh kosong.")

    for item in kebutuhan_host:
        if not isinstance(item, int) or isinstance(item, bool) or item < 1:
            raise ValueError("Setiap kebutuhan host harus berupa bilangan bulat minimal 1.")

    total_parent_ips = 1 << (32 - parent_prefix)
    end_parent_int = ip_int + total_parent_ips - 1

    sorted_needs = sorted(kebutuhan_host, reverse=True)
    allocations: list[dict[str, Any]] = []
    current_net_int = ip_int

    for need in sorted_needs:
        # Ukuran blok pangkat 2 terkecil >= need + 2, minimal /30 (2 host bit = 4 IP)
        host_bits = 2
        while (1 << host_bits) < need + 2:
            host_bits += 1

        new_prefix = 32 - host_bits
        block_size = 1 << host_bits

        if new_prefix < parent_prefix or (current_net_int + block_size - 1) > end_parent_int:
            raise ValueError("Kapasitas blok jaringan induk tidak mencukupi untuk seluruh kebutuhan host.")

        sub_ip = _int_to_ip(current_net_int)
        subnet_info = hitung_subnet(sub_ip, new_prefix)
        allocations.append(
            {
                "kebutuhan": need,
                "network_cidr": f"{sub_ip}/{new_prefix}",
                **subnet_info,
            }
        )
        current_net_int += block_size

    return allocations


class VlsmRequest(BaseModel):
    network: str
    kebutuhan_host: list[int]


@app.get("/")
def read_index() -> FileResponse:
    """Menyajikan halaman utama aplikasi web."""
    return FileResponse(BASE_DIR / "index.html")


@app.get("/api/subnet")
def api_subnet(ip: str = "", prefix: str = "") -> dict[str, Any]:
    """Endpoint perhitungan subnet IPv4."""
    try:
        if not prefix or not prefix.lstrip("-").isdigit():
            raise ValueError("Prefix harus berupa bilangan bulat antara 0 sampai 32.")
        prefix_int = int(prefix)
        return hitung_subnet(ip, prefix_int)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/vlsm")
def api_vlsm(payload: VlsmRequest) -> list[dict[str, Any]]:
    """Endpoint perhitungan alokasi VLSM."""
    try:
        return alokasi_vlsm(payload.network, payload.kebutuhan_host)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
