# -*- coding: utf-8 -*-
"""
Adega PDV – Wine UI (Tkinter + ttkbootstrap)
Stack: Python 3.10+, Tkinter, ttkbootstrap, MySQL (mysql-connector-python), python-escpos (opcional)

Destaques visuais:
- Tema escuro elegante (ttkbootstrap "darkly") com acentos em vinho/bordô
- Topbar com identidade da adega e status
- Sidebar de navegação com ícones (emoji) e realce de página ativa
- Cartões/frames mais "clean" e espaçosos
- Status bar com relógio
- Mantém todas as funções: Fornecedores, Usuários, Filtros, Importação CSV, QR PIX com atendente

Dependências:
    pip install ttkbootstrap
    pip install mysql-connector-python
    pip install python-escpos pyusb   # (opcional para impressão)
"""
import os
import csv
from datetime import datetime, date, timedelta
from decimal import Decimal, ROUND_HALF_UP
import hashlib, secrets

import tkinter as tk
from tkinter import ttk, messagebox, filedialog, simpledialog

# ttkbootstrap para visual moderno
try:
    import ttkbootstrap as tb
    from ttkbootstrap.constants import *
except ImportError:
    raise SystemExit("Falta instalar 'ttkbootstrap'. Use: pip install ttkbootstrap")

# Dependências externas
try:
    import mysql.connector
except ImportError:
    raise SystemExit("Falta instalar 'mysql-connector-python'. Use: pip install mysql-connector-python")

# Impressora ESC/POS é opcional
try:
    from escpos.printer import Usb, Serial, Network
    ESCPOS_AVAILABLE = True
except Exception:
    ESCPOS_AVAILABLE = False

# ===================== CONFIG / TEMA =====================
DB_CONFIG = {
    "host": os.environ.get("ADEGA_DB_HOST", "127.0.0.1"),
    "user": os.environ.get("ADEGA_DB_USER", "root"),
    "password": os.environ.get("ADEGA_DB_PASS", ""),
    "database": os.environ.get("ADEGA_DB_NAME", "adega_pdv"),
    "port": int(os.environ.get("ADEGA_DB_PORT", "3306")),
}

# Paleta "vinho"
WINE = "#6A1B2D"      # bordô principal
WINE_DARK = "#4A0F1F"  # mais escuro
WINE_LIGHT = "#9A2C4A" # destaque

MONEY_Q = Decimal("0.01")

def to_decimal(x) -> Decimal:
    if x is None:
        return Decimal("0")
    if isinstance(x, Decimal):
        return x
    s = str(x).replace(",", ".").strip()
    if s == "":
        return Decimal("0")
    return Decimal(s)

def money(x: Decimal) -> str:
    return f"R$ {x.quantize(MONEY_Q, rounding=ROUND_HALF_UP):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

def hash_password(password: str, salt: bytes = None) -> str:
    salt = salt or secrets.token_bytes(16)
    h = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 200_000)
    return salt.hex() + ":" + h.hex()

def verify_password(password: str, stored: str) -> bool:
    try:
        salt_hex, hash_hex = stored.split(":", 1)
        salt = bytes.fromhex(salt_hex)
        h = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 200_000)
        return h.hex() == hash_hex
    except Exception:
        return False

# ===================== ACESSO AO BANCO =====================
class DB:
    def __init__(self, config: dict):
        self.config = config
        self.conn = None

    def connect(self):
        try:
            self.conn = mysql.connector.connect(**self.config)
        except mysql.connector.errors.ProgrammingError as e:
            if "Unknown database" in str(e):
                tmp = self.config.copy()
                dbname = tmp.pop("database")
                conn = mysql.connector.connect(**tmp)
                cur = conn.cursor()
                cur.execute(f"CREATE DATABASE IF NOT EXISTS `{dbname}` DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
                conn.commit()
                cur.close()
                conn.close()
                self.conn = mysql.connector.connect(**self.config)
            else:
                raise

    def cursor(self):
        if not self.conn or not self.conn.is_connected():
            self.connect()
        return self.conn.cursor()

    def execute(self, sql, params=None):
        cur = self.cursor()
        cur.execute(sql, params or ())
        return cur

    def executemany(self, sql, seq):
        cur = self.cursor()
        cur.executemany(sql, seq)
        return cur

    def commit(self):
        if self.conn:
            self.conn.commit()

    def close(self):
        if self.conn and self.conn.is_connected():
            self.conn.close()

# ===================== SCHEMA =====================
SCHEMA_SQL = [
    # users
    """
    CREATE TABLE IF NOT EXISTS users (
        id INT AUTO_INCREMENT PRIMARY KEY,
        username VARCHAR(50) UNIQUE NOT NULL,
        password_hash VARCHAR(255) NOT NULL,
        role ENUM('admin','gerente','caixa') NOT NULL DEFAULT 'caixa',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """,
    # suppliers
    """
    CREATE TABLE IF NOT EXISTS suppliers (
        id INT AUTO_INCREMENT PRIMARY KEY,
        name VARCHAR(120) NOT NULL,
        document VARCHAR(40) NULL,
        phone VARCHAR(40) NULL,
        email VARCHAR(120) NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """,
    # products
    """
    CREATE TABLE IF NOT EXISTS products (
        id INT AUTO_INCREMENT PRIMARY KEY,
        sku VARCHAR(40) UNIQUE NOT NULL,
        barcode VARCHAR(32) UNIQUE,
        name VARCHAR(180) NOT NULL,
        item_type ENUM('Vinho','Cerveja','Destilado','Outros') NOT NULL DEFAULT 'Outros',
        category VARCHAR(80),
        brand VARCHAR(120),
        varietal VARCHAR(120),
        vintage YEAR NULL,
        volume_ml INT,
        abv DECIMAL(5,2),
        country VARCHAR(80),
        region VARCHAR(120),
        supplier_id INT NULL,
        cost_price DECIMAL(10,2) NOT NULL DEFAULT 0,
        margin_pct DECIMAL(6,2) NOT NULL DEFAULT 0,
        sale_price DECIMAL(10,2) NOT NULL DEFAULT 0,
        stock_qty INT NOT NULL DEFAULT 0,
        min_stock INT NOT NULL DEFAULT 0,
        lot_code VARCHAR(60) NULL,
        expiry DATE NULL,
        active TINYINT(1) NOT NULL DEFAULT 1,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP NULL,
        CONSTRAINT fk_products_supplier FOREIGN KEY (supplier_id) REFERENCES suppliers(id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """,
    # sales
    """
    CREATE TABLE IF NOT EXISTS sales (
        id BIGINT AUTO_INCREMENT PRIMARY KEY,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        user_id INT NOT NULL,
        payment_method ENUM('Dinheiro','Crédito','Débito','PIX') NOT NULL,
        subtotal DECIMAL(10,2) NOT NULL DEFAULT 0,
        discount DECIMAL(10,2) NOT NULL DEFAULT 0,
        total DECIMAL(10,2) NOT NULL DEFAULT 0,
        received DECIMAL(10,2) NOT NULL DEFAULT 0,
        change_due DECIMAL(10,2) NOT NULL DEFAULT 0,
        CONSTRAINT fk_sales_user FOREIGN KEY (user_id) REFERENCES users(id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """,
    # sale_items
    """
    CREATE TABLE IF NOT EXISTS sale_items (
        id BIGINT AUTO_INCREMENT PRIMARY KEY,
        sale_id BIGINT NOT NULL,
        product_id INT NOT NULL,
        qty INT NOT NULL,
        unit_price DECIMAL(10,2) NOT NULL,
        unit_cost DECIMAL(10,2) NOT NULL,
        margin_pct DECIMAL(6,2) NOT NULL DEFAULT 0,
        line_total DECIMAL(10,2) NOT NULL,
        line_profit DECIMAL(10,2) NOT NULL,
        CONSTRAINT fk_items_sale FOREIGN KEY (sale_id) REFERENCES sales(id),
        CONSTRAINT fk_items_product FOREIGN KEY (product_id) REFERENCES products(id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """,
    # settings (loja + impressora + PIX)
    """
    CREATE TABLE IF NOT EXISTS settings (
        id TINYINT PRIMARY KEY,
        store_name VARCHAR(120) NOT NULL,
        store_document VARCHAR(40) NULL,
        store_address VARCHAR(200) NULL,
        store_phone VARCHAR(60) NULL,
        receipt_footer VARCHAR(240) NULL,
        print_enabled TINYINT(1) NOT NULL DEFAULT 0,
        printer_kind ENUM('USB','Serial','Network') DEFAULT 'USB',
        usb_vendor_id VARCHAR(8) NULL,
        usb_product_id VARCHAR(8) NULL,
        usb_in_ep VARCHAR(8) NULL,
        usb_out_ep VARCHAR(8) NULL,
        serial_device VARCHAR(120) NULL,
        serial_baud INT NULL,
        network_host VARCHAR(120) NULL,
        network_port INT NULL,
        pix_key VARCHAR(140) NULL,
        pix_merchant_city VARCHAR(60) NULL
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """,
]

DEFAULT_SETTINGS = {
    "id": 1,
    "store_name": "Minha Adega",
    "store_document": "",
    "store_address": "",
    "store_phone": "",
    "receipt_footer": "SEM VALOR FISCAL",
    "print_enabled": 0,
    "printer_kind": "USB",
    "usb_vendor_id": "",
    "usb_product_id": "",
    "usb_in_ep": "",
    "usb_out_ep": "",
    "serial_device": "",
    "serial_baud": 9600,
    "network_host": "",
    "network_port": 9100,
    "pix_key": "",
    "pix_merchant_city": "SAO PAULO",
}

def ensure_settings_columns(db: "DB"):
    """Auto-migra colunas que podem faltar em settings (ao atualizar)."""
    try:
        cur = db.execute("SHOW COLUMNS FROM settings")
        existing = {r[0] for r in cur.fetchall()}
    except mysql.connector.Error:
        return
    to_add = []
    if "pix_key" not in existing:
        to_add.append("ADD COLUMN pix_key VARCHAR(140) NULL")
    if "pix_merchant_city" not in existing:
        to_add.append("ADD COLUMN pix_merchant_city VARCHAR(60) NULL")
    if to_add:
        db.execute("ALTER TABLE settings " + ", ".join(to_add))
        db.commit()

def init_database(db: "DB"):
    for sql in SCHEMA_SQL:
        db.execute(sql)
    db.commit()
    ensure_settings_columns(db)

    cur = db.execute("SELECT COUNT(*) FROM users")
    (count_users,) = cur.fetchone()
    if count_users == 0:
        db.execute("INSERT INTO users (username, password_hash, role) VALUES (%s,%s,'admin')",
                   ("admin", hash_password("admin")))
        db.commit()

    cur = db.execute("SELECT COUNT(*) FROM settings WHERE id=1")
    (cnt,) = cur.fetchone()
    if cnt == 0:
        cols = ",".join(DEFAULT_SETTINGS.keys())
        placeholders = ",".join(["%s"] * len(DEFAULT_SETTINGS))
        db.execute(f"INSERT INTO settings ({cols}) VALUES ({placeholders})", tuple(DEFAULT_SETTINGS.values()))
        db.commit()

# ===================== PIX (EMV/BR Code) =====================
def _emv_kv(_id: str, value: str) -> str:
    return f"{_id}{len(value):02d}{value}"
def _crc16_ccitt(data: bytes) -> int:
    crc = 0xFFFF
    for b in data:
        crc ^= (b << 8)
        for _ in range(8):
            if (crc & 0x8000) != 0:
                crc = (crc << 1) ^ 0x1021
            else:
                crc <<= 1
            crc &= 0xFFFF
    return crc
def build_pix_payload(key: str, merchant_name: str, merchant_city: str, amount: Decimal = None, txid: str = "PDVSALE") -> str:
    if not key or not merchant_name or not merchant_city: return ""
    gui = _emv_kv("00", "BR.GOV.BCB.PIX")
    acc = gui + _emv_kv("01", key)
    mai = _emv_kv("26", acc)
    pfi = _emv_kv("00", "01")
    mcc = _emv_kv("52", "0000")
    cur = _emv_kv("53", "986")
    amt = _emv_kv("54", f"{amount.quantize(MONEY_Q)}") if amount and amount > 0 else ""
    cty = _emv_kv("58", "BR")
    mname = _emv_kv("59", merchant_name[:25] or "LOJA")
    mcity = _emv_kv("60", merchant_city[:15] or "CIDADE")
    tx = _emv_kv("05", txid[:25])
    add = _emv_kv("62", tx)
    partial = pfi + mai + mcc + cur + amt + cty + mname + mcity + add + "6304"
    crc = _crc16_ccitt(partial.encode("utf-8"))
    crc_str = f"{crc:04X}"
    return partial + crc_str

# ===================== IMPRESSORA =====================
class ReceiptPrinter:
    def __init__(self, db: DB):
        self.db = db
        self.enabled = False
        self.kind = "USB"
        self.device = None
        self.store = {}
        self._load()

    def _load(self):
        cur = self.db.execute("SELECT * FROM settings WHERE id=1")
        row = cur.fetchone()
        if not row:
            return
        cols = [d[0] for d in cur.description]
        self.store = dict(zip(cols, row))
        self.enabled = bool(self.store.get("print_enabled")) and ESCPOS_AVAILABLE
        self.kind = self.store.get("printer_kind", "USB")

        if not self.enabled:
            return

        try:
            if self.kind == "USB":
                vid = int((self.store.get("usb_vendor_id") or "0"), 16)
                pid = int((self.store.get("usb_product_id") or "0"), 16)
                in_ep = self.store.get("usb_in_ep") or None
                out_ep = self.store.get("usb_out_ep") or None
                self.device = Usb(vid, pid, in_ep=in_ep, out_ep=out_ep, timeout=0, autoflush=True)
            elif self.kind == "Serial":
                dev = self.store.get("serial_device") or "COM3"
                baud = int(self.store.get("serial_baud") or 9600)
                self.device = Serial(dev, baudrate=baud)
            elif self.kind == "Network":
                host = self.store.get("network_host") or "127.0.0.1"
                port = int(self.store.get("network_port") or 9100)
                self.device = Network(host, port=port, timeout=10)
        except Exception as e:
            print("[AVISO] Falha ao conectar impressora ESC/POS:", e)
            self.device = None
            self.enabled = False

    def print_receipt(self, sale: dict, items: list, attendant_name: str, pix_payload: str = ""):
        """Imprime recibo 58mm com identificação do atendente e QR PIX quando aplicável."""
        if not self.enabled or not self.device:
            print("[INFO] Impressora desabilitada ou indisponível. Recibo não impresso.")
            return

        p = self.device
        try:
            store_name = self.store.get("store_name") or "Minha Adega"
            p.set(align="center", text_type="B", width=2, height=2)
            p.text(store_name + "\n")
            p.set(align="center", text_type="A", width=1, height=1)
            if self.store.get("store_address"):
                p.text(self.store.get("store_address") + "\n")
            if self.store.get("store_phone"):
                p.text("Tel: " + self.store.get("store_phone") + "\n")
            p.text("\n")

            p.set(align="left")
            p.text(f"Data: {sale['created_at'].strftime('%d/%m/%Y %H:%M:%S')}\n")
            p.text(f"Venda: {sale['id']}\n")
            p.text(f"Atendente: {attendant_name}\n")
            p.text("-"*32 + "\n")
            p.text("ITEM               QTD   TOTAL\n")
            p.text("-"*32 + "\n")

            for it in items:
                name = it['name'][:16]
                total = money(it['line_total'])
                qty = str(it['qty']).rjust(3)
                p.text(f"{name:<16}{qty}  {total:>10}\n")
                p.text(f"  {money(Decimal(it['unit_price']))} x {it['qty']}\n")

            p.text("-"*32 + "\n")
            p.set(align="right")
            p.text(f"Subtotal: {money(Decimal(sale['subtotal']))}\n")
            if Decimal(sale['discount']) > 0:
                p.text(f"Desconto: {money(Decimal(sale['discount']))}\n")
            p.text(f"TOTAL: {money(Decimal(sale['total']))}\n")
            p.text(f"Pgto: {sale['payment_method']}\n")
            if Decimal(sale['received']) > 0:
                p.text(f"Recebido: {money(Decimal(sale['received']))}\n")
                p.text(f"Troco: {money(Decimal(sale['change_due']))}\n")
            p.text("\n")

            # PIX QR
            if sale['payment_method'] == "PIX" and pix_payload:
                p.set(align="center")
                try:
                    # Tamanho padrão aceitável em 58mm
                    p.qr(pix_payload, size=6)
                    p.text("Escaneie para pagar via PIX\n")
                except Exception as e:
                    p.text("[Falha ao gerar QR PIX]\n")
                    print("Erro QR:", e)

            p.set(align="center")
            footer = self.store.get("receipt_footer") or "SEM VALOR FISCAL"
            p.text(footer + "\n")
            p.cut()
        except Exception as e:
            print("[ERRO] Falha na impressão:", e)

# ===================== REPOSITÓRIOS =====================
class UserRepo:
    def __init__(self, db: DB):
        self.db = db
    def get_by_username(self, username: str):
        cur = self.db.execute("SELECT id, username, password_hash, role FROM users WHERE username=%s", (username,))
        return cur.fetchone()
    def list_all(self):
        cur = self.db.execute("SELECT id, username, role, created_at FROM users ORDER BY username")
        return cur.fetchall()
    def create_user(self, username: str, password: str, role: str):
        ph = hash_password(password)
        self.db.execute("INSERT INTO users (username, password_hash, role) VALUES (%s,%s,%s)", (username, ph, role))
        self.db.commit()
    def set_password(self, user_id: int, new_password: str):
        ph = hash_password(new_password)
        self.db.execute("UPDATE users SET password_hash=%s WHERE id=%s", (ph, user_id))
        self.db.commit()
    def set_role(self, user_id: int, new_role: str):
        self.db.execute("UPDATE users SET role=%s WHERE id=%s", (new_role, user_id))
        self.db.commit()
    def delete_user(self, user_id: int):
        self.db.execute("DELETE FROM users WHERE id=%s", (user_id,))
        self.db.commit()

class SupplierRepo:
    def __init__(self, db: DB):
        self.db = db
    def list_all(self, term: str = ""):
        like = f"%{term}%"
        cur = self.db.execute(
            "SELECT id, name, document, phone, email, created_at FROM suppliers "
            "WHERE name LIKE %s OR document LIKE %s OR phone LIKE %s OR email LIKE %s "
            "ORDER BY name LIMIT 500",
            (like, like, like, like)
        )
        return cur.fetchall()
    def upsert(self, data: dict):
        name = data.get("name","").strip()
        if not name:
            raise ValueError("Nome do fornecedor é obrigatório.")
        if data.get("id"):
            self.db.execute("UPDATE suppliers SET name=%s, document=%s, phone=%s, email=%s WHERE id=%s",
                            (data["name"], data.get("document"), data.get("phone"), data.get("email"), int(data["id"])))
        else:
            cur = self.db.execute("SELECT id FROM suppliers WHERE name=%s", (name,))
            row = cur.fetchone()
            if row:
                self.db.execute("UPDATE suppliers SET document=%s, phone=%s, email=%s WHERE id=%s",
                                (data.get("document"), data.get("phone"), data.get("email"), row[0]))
            else:
                self.db.execute("INSERT INTO suppliers (name, document, phone, email) VALUES (%s,%s,%s,%s)",
                                (data["name"], data.get("document"), data.get("phone"), data.get("email")))
        self.db.commit()
    def delete(self, supplier_id: int):
        self.db.execute("UPDATE products SET supplier_id=NULL WHERE supplier_id=%s", (supplier_id,))
        self.db.execute("DELETE FROM suppliers WHERE id=%s", (supplier_id,))
        self.db.commit()

class ProductRepo:
    def __init__(self, db: DB):
        self.db = db
    def upsert(self, data: dict):
        cost = to_decimal(data.get('cost_price'))
        margin = to_decimal(data.get('margin_pct'))
        sale_price = (cost * (Decimal('1.0') + (margin/Decimal('100')))).quantize(MONEY_Q)
        data['sale_price'] = sale_price
        data['updated_at'] = datetime.now()
        cur = self.db.execute("SELECT id FROM products WHERE sku=%s", (data['sku'],))
        row = cur.fetchone()
        cols = [
            'sku','barcode','name','item_type','category','brand','varietal','vintage','volume_ml','abv','country','region',
            'supplier_id','cost_price','margin_pct','sale_price','stock_qty','min_stock','lot_code','expiry','active','updated_at'
        ]
        vals = tuple(data.get(c) for c in cols)
        if row:
            set_clause = ",".join([f"{c}=%s" for c in cols])
            self.db.execute(f"UPDATE products SET {set_clause} WHERE id=%s", vals + (row[0],))
        else:
            cols2 = cols + ['created_at']
            placeholders = ",".join(["%s"] * len(cols2))
            vals2 = vals + (datetime.now(),)
            self.db.execute(f"INSERT INTO products ({','.join(cols2)}) VALUES ({placeholders})", vals2)
        self.db.commit()
    def search(self, term: str, category: str = "", brand: str = ""):
        like = f"%{term}%"
        where = ["(sku LIKE %s OR barcode LIKE %s OR name LIKE %s)"]
        params = [like, like, like]
        if category and category != "Todas":
            where.append("IFNULL(category,'') = %s")
            params.append(category)
        if brand and brand != "Todas":
            where.append("IFNULL(brand,'') = %s")
            params.append(brand)
        sql = f"""
            SELECT p.id, sku, barcode, name, item_type, category, brand, sale_price, stock_qty, min_stock, expiry
            FROM products p
            WHERE {' AND '.join(where)}
            ORDER BY name
            LIMIT 400
        """
        cur = self.db.execute(sql, tuple(params))
        return cur.fetchall()
    def get_filters(self):
        cur = self.db.execute("SELECT DISTINCT category FROM products WHERE category IS NOT NULL AND category<>'' ORDER BY category")
        categories = ["Todas"] + [r[0] for r in cur.fetchall()]
        cur = self.db.execute("SELECT DISTINCT brand FROM products WHERE brand IS NOT NULL AND brand<>'' ORDER BY brand")
        brands = ["Todas"] + [r[0] for r in cur.fetchall()]
        return categories, brands
    def get_by_barcode(self, barcode: str):
        cur = self.db.execute("SELECT id, name, sale_price, stock_qty, cost_price, margin_pct FROM products WHERE barcode=%s", (barcode,))
        return cur.fetchone()
    def adjust_stock(self, product_id: int, delta_qty: int):
        self.db.execute("UPDATE products SET stock_qty = stock_qty + %s, updated_at=NOW() WHERE id=%s", (delta_qty, product_id))
        self.db.commit()

class SalesRepo:
    def __init__(self, db: DB):
        self.db = db
    def create_sale(self, user_id: int, payment_method: str, subtotal: Decimal, discount: Decimal, total: Decimal, received: Decimal, change_due: Decimal):
        cur = self.db.execute(
            "INSERT INTO sales (user_id, payment_method, subtotal, discount, total, received, change_due) VALUES (%s,%s,%s,%s,%s,%s,%s)",
            (user_id, payment_method, float(subtotal), float(discount), float(total), float(received), float(change_due))
        )
        self.db.commit()
        return cur.lastrowid

    def add_item(self, sale_id: int, product_id: int, qty: int, unit_price: Decimal, unit_cost: Decimal, margin_pct: Decimal):
        line_total = (unit_price * qty).quantize(MONEY_Q)
        line_profit = ((unit_price - unit_cost) * qty).quantize(MONEY_Q)
        self.db.execute(
            "INSERT INTO sale_items (sale_id, product_id, qty, unit_price, unit_cost, margin_pct, line_total, line_profit) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
            (sale_id, product_id, qty, float(unit_price), float(unit_cost), float(margin_pct), float(line_total), float(line_profit))
        )
        self.db.commit()
        return {"line_total": line_total, "line_profit": line_profit}

    # Relatórios
    def report_sales(self, start: datetime, end: datetime):
        cur = self.db.execute(
            "SELECT id, created_at, payment_method, subtotal, discount, total FROM sales WHERE created_at BETWEEN %s AND %s ORDER BY created_at",
            (start, end)
        )
        return cur.fetchall()
    def report_profit(self, start: datetime, end: datetime):
        cur = self.db.execute(
            "SELECT s.id, s.created_at, SUM(si.line_profit) FROM sales s JOIN sale_items si ON si.sale_id = s.id WHERE s.created_at BETWEEN %s AND %s GROUP BY s.id, s.created_at ORDER BY s.created_at",
            (start, end)
        )
        return cur.fetchall()
    def report_top_products(self, start: datetime, end: datetime, limit: int = 20):
        cur = self.db.execute(
            "SELECT p.name, SUM(si.qty) AS qtd, SUM(si.line_total) AS total FROM sale_items si JOIN sales s ON s.id = si.sale_id JOIN products p ON p.id = si.product_id WHERE s.created_at BETWEEN %s AND %s GROUP BY p.name ORDER BY qtd DESC LIMIT %s",
            (start, end, limit)
        )
        return cur.fetchall()
    def report_low_stock(self):
        cur = self.db.execute("SELECT sku, barcode, name, stock_qty, min_stock FROM products WHERE active=1 AND stock_qty <= min_stock ORDER BY stock_qty ASC")
        return cur.fetchall()
    def report_expiring(self, days: int = 30):
        cur = self.db.execute("SELECT sku, barcode, name, expiry, stock_qty FROM products WHERE expiry IS NOT NULL AND expiry <= %s ORDER BY expiry",
                              (date.today() + timedelta(days=days),))
        return cur.fetchall()

# ===================== IMPRESSORA =====================
class ReceiptPrinter:
    def __init__(self, db: DB):
        self.db = db; self.enabled = False; self.kind = "USB"; self.device = None; self.store = {}
        self._load()
    def _load(self):
        cur = self.db.execute("SELECT * FROM settings WHERE id=1")
        row = cur.fetchone()
        if not row: return
        cols = [d[0] for d in cur.description]; self.store = dict(zip(cols, row))
        self.enabled = bool(self.store.get("print_enabled")) and ESCPOS_AVAILABLE
        self.kind = self.store.get("printer_kind", "USB")
        if not self.enabled: return
        try:
            if self.kind == "USB":
                vid = int((self.store.get("usb_vendor_id") or "0"), 16)
                pid = int((self.store.get("usb_product_id") or "0"), 16)
                in_ep = self.store.get("usb_in_ep") or None
                out_ep = self.store.get("usb_out_ep") or None
                self.device = Usb(vid, pid, in_ep=in_ep, out_ep=out_ep, timeout=0, autoflush=True)
            elif self.kind == "Serial":
                dev = self.store.get("serial_device") or "COM3"; baud = int(self.store.get("serial_baud") or 9600)
                self.device = Serial(dev, baudrate=baud)
            elif self.kind == "Network":
                host = self.store.get("network_host") or "127.0.0.1"; port = int(self.store.get("network_port") or 9100)
                self.device = Network(host, port=port, timeout=10)
        except Exception as e:
            print("[AVISO] Falha ao conectar impressora ESC/POS:", e); self.device = None; self.enabled = False
    def print_receipt(self, sale: dict, items: list, attendant_name: str, pix_payload: str = ""):
        if not self.enabled or not self.device:
            print("[INFO] Impressora desabilitada ou indisponível. Recibo não impresso."); return
        p = self.device
        try:
            store_name = self.store.get("store_name") or "Minha Adega"
            p.set(align="center", text_type="B", width=2, height=2); p.text(store_name + "\n")
            p.set(align="center", text_type="A", width=1, height=1)
            if self.store.get("store_address"): p.text(self.store.get("store_address") + "\n")
            if self.store.get("store_phone"): p.text("Tel: " + self.store.get("store_phone") + "\n")
            p.text("\n")
            p.set(align="left")
            p.text(f"Data: {sale['created_at'].strftime('%d/%m/%Y %H:%M:%S')}\n")
            p.text(f"Venda: {sale['id']}\n")
            p.text(f"Atendente: {attendant_name}\n")
            p.text("-"*32 + "\n"); p.text("ITEM               QTD   TOTAL\n"); p.text("-"*32 + "\n")
            for it in items:
                name = it['name'][:16]; total = money(it['line_total']); qty = str(it['qty']).rjust(3)
                p.text(f"{name:<16}{qty}  {total:>10}\n"); p.text(f"  {money(Decimal(it['unit_price']))} x {it['qty']}\n")
            p.text("-"*32 + "\n"); p.set(align="right")
            p.text(f"Subtotal: {money(Decimal(sale['subtotal']))}\n")
            if Decimal(sale['discount']) > 0: p.text(f"Desconto: {money(Decimal(sale['discount']))}\n")
            p.text(f"TOTAL: {money(Decimal(sale['total']))}\n"); p.text(f"Pgto: {sale['payment_method']}\n")
            if Decimal(sale['received']) > 0:
                p.text(f"Recebido: {money(Decimal(sale['received']))}\n"); p.text(f"Troco: {money(Decimal(sale['change_due']))}\n")
            p.text("\n")
            if sale['payment_method'] == "PIX" and pix_payload:
                p.set(align="center")
                try:
                    p.qr(pix_payload, size=6); p.text("Escaneie para pagar via PIX\n")
                except Exception as e:
                    p.text("[Falha ao gerar QR PIX]\n"); print("Erro QR:", e)
            p.set(align="center"); footer = self.store.get("receipt_footer") or "SEM VALOR FISCAL"
            p.text(footer + "\n"); p.cut()
        except Exception as e:
            print("[ERRO] Falha na impressão:", e)

# ===================== UI PAGES =====================
class ProductForm(tb.Labelframe):
    def __init__(self, master, on_save, on_clear):
        super().__init__(master, text="Cadastro de Produto", bootstyle=INFO)
        self.on_save = on_save; self.on_clear = on_clear
        self.vars = {k: tk.StringVar() for k in [
            'sku','barcode','name','item_type','category','brand','varietal','vintage','volume_ml','abv','country','region',
            'supplier_id','cost_price','margin_pct','sale_price','stock_qty','min_stock','lot_code','expiry','active'
        ]}
        self.vars['item_type'].set('Outros'); self.vars['active'].set('1')
        grid = [
            ('SKU','sku'),('Código barras','barcode'),('Nome','name'),('Tipo','item_type'),
            ('Categoria','category'),('Marca/Produtor','brand'),('Uva/Estilo','varietal'),('Safra','vintage'),
            ('Volume (mL)','volume_ml'),('ABV %','abv'),('País','country'),('Região','region'),
            ('Fornecedor (ID)','supplier_id'),('Preço compra','cost_price'),('Margem %','margin_pct'),('Preço venda','sale_price'),
            ('Estoque','stock_qty'),('Estoque mín.','min_stock'),('Lote','lot_code'),('Validade (AAAA-MM-DD)','expiry'),
        ]
        for i, (lbl, key) in enumerate(grid):
            ttk.Label(self, text=lbl).grid(row=i//4, column=(i%4)*2, sticky="e", padx=6, pady=4)
            if key == 'item_type':
                cb = tb.Combobox(self, textvariable=self.vars[key], values=['Vinho','Cerveja','Destilado','Outros'], state='readonly', width=20)
                cb.grid(row=i//4, column=(i%4)*2+1, sticky="we", padx=6, pady=4)
            else:
                ent = ttk.Entry(self, textvariable=self.vars[key])
                ent.grid(row=i//4, column=(i%4)*2+1, sticky="we", padx=6, pady=4)
        ttk.Label(self, text="Ativo (1/0)").grid(row=5, column=6, sticky="e", padx=6, pady=4)
        ttk.Entry(self, textvariable=self.vars['active']).grid(row=5, column=7, sticky="we", padx=6, pady=4)
        btns = ttk.Frame(self); btns.grid(row=6, column=0, columnspan=8, sticky="we", pady=8)
        tb.Button(btns, text="Salvar/Atualizar", command=self._save, bootstyle=SUCCESS).pack(side="left", padx=6)
        tb.Button(btns, text="Limpar", command=self._clear, bootstyle=SECONDARY).pack(side="left", padx=6)
        for c in range(8): self.columnconfigure(c, weight=1)
    def _save(self):
        data = {k: v.get().strip() for k, v in self.vars.items()}
        data['cost_price'] = to_decimal(data['cost_price']); data['margin_pct'] = to_decimal(data['margin_pct'])
        data['sale_price'] = to_decimal(data.get('sale_price') or 0); data['stock_qty'] = int(data['stock_qty'] or 0)
        data['min_stock'] = int(data['min_stock'] or 0); data['supplier_id'] = int(data['supplier_id'] or 0) or None
        data['vintage'] = int(data['vintage'] or 0) or None; data['volume_ml'] = int(data['volume_ml'] or 0) or None
        data['abv'] = to_decimal(data['abv'] or 0); data['expiry'] = data['expiry'] or None; data['active'] = int(data['active'] or 1)
        self.on_save(data)
    def _clear(self):
        for v in self.vars.values(): v.set("")
        self.vars['item_type'].set('Outros'); self.vars['active'].set('1'); self.on_clear()

class ProductPage(tb.Frame):
    def __init__(self, master, repo):
        super().__init__(master)
        self.repo = repo
        self.form = ProductForm(self, on_save=self.save_product, on_clear=lambda: None)
        self.form.pack(fill="x", padx=12, pady=12)
        searchf = tb.Frame(self); searchf.pack(fill="x", padx=12)
        ttk.Label(searchf, text="Buscar").pack(side="left")
        self.ent_search = ttk.Entry(searchf, width=30); self.ent_search.pack(side="left", padx=6)
        ttk.Label(searchf, text="Categoria").pack(side="left", padx=(12, 2))
        self.cmb_cat = tb.Combobox(searchf, state="readonly", width=22)
        ttk.Label(searchf, text="Marca").pack(side="left", padx=(12, 2))
        self.cmb_brand = tb.Combobox(searchf, state="readonly", width=22)
        tb.Button(searchf, text="Filtrar", command=self.refresh_list, bootstyle=PRIMARY).pack(side="left", padx=6)
        tb.Button(searchf, text="Importar CSV", command=self.import_csv, bootstyle=INFO).pack(side="left", padx=6)

        cols = ("id","sku","barcode","name","item_type","category","brand","sale_price","stock_qty","min_stock","expiry")
        self.tree = tb.Treeview(self, columns=cols, show="headings", height=12, bootstyle=INFO)
        for c in cols:
            self.tree.heading(c, text=c); self.tree.column(c, width=110)
        self.tree.pack(fill="both", expand=True, padx=12, pady=12)
        self._load_filters(); self.refresh_list()
    def _load_filters(self):
        cats, brands = self.repo.get_filters()
        self.cmb_cat["values"] = cats; self.cmb_brand["values"] = brands
        if cats: self.cmb_cat.set(cats[0]); 
        if brands: self.cmb_brand.set(brands[0])
    def save_product(self, data: dict):
        try:
            if not data['sku'] or not data['name']:
                messagebox.showwarning("Atenção", "SKU e Nome são obrigatórios."); return
            self.repo.upsert(data); messagebox.showinfo("OK", "Produto salvo/atualizado.")
            self._load_filters(); self.refresh_list()
        except Exception as e:
            messagebox.showerror("Erro", f"Falha ao salvar: {e}")
    def refresh_list(self):
        term = self.ent_search.get().strip(); cat = self.cmb_cat.get().strip(); brand = self.cmb_brand.get().strip()
        rows = self.repo.search(term, cat, brand)
        for i in self.tree.get_children(): self.tree.delete(i)
        for r in rows: self.tree.insert('', 'end', values=r)
    def import_csv(self):
        path = filedialog.askopenfilename(filetypes=[("CSV","*.csv")])
        if not path: return
        count=0; errors=0
        with open(path, newline='', encoding='utf-8') as f:
            reader = csv.DictReader(f, delimiter=';')
            for row in reader:
                try:
                    data = {k: (row.get(k,"").strip()) for k in row.keys()}
                    for k in ("vintage","volume_ml","supplier_id","stock_qty","min_stock","active"):
                        if k in data: data[k] = int(data[k]) if data[k] else 0
                    for k in ("cost_price","margin_pct","abv"):
                        if k in data: data[k] = to_decimal(data[k])
                    if not data.get("expiry"): data["expiry"] = None
                    data["supplier_id"] = data["supplier_id"] or None; data["vintage"] = data["vintage"] or None; data["volume_ml"] = data["volume_ml"] or None
                    data["active"] = int(data.get("active") or 1)
                    self.repo.upsert(data); count += 1
                except Exception:
                    errors += 1
        self._load_filters(); self.refresh_list(); messagebox.showinfo("Importação", f"Importados: {count} | Erros: {errors}")

class PosPage(tb.Frame):
    def __init__(self, master, product_repo, sales_repo, printer, state):
        super().__init__(master)
        self.product_repo = product_repo; self.sales_repo = sales_repo; self.printer = printer; self.state = state
        bar = tb.Frame(self); bar.pack(fill="x", padx=12, pady=8)
        tb.Label(bar, text="Código de barras").pack(side="left")
        self.ent_barcode = tb.Entry(bar); self.ent_barcode.pack(side="left", fill="x", expand=True, padx=8)
        self.ent_barcode.bind("<Return>", self.add_by_barcode)
        tb.Button(bar, text="Adicionar", command=self.add_by_barcode, bootstyle=SUCCESS).pack(side="left")

        cols = ("product_id","name","qty","unit_price","line_total")
        self.cart = tb.Treeview(self, columns=cols, show="headings", height=12, bootstyle=WARNING)
        for c in cols: self.cart.heading(c, text=c); self.cart.column(c, width=150)
        self.cart.pack(fill="both", expand=True, padx=12, pady=12)

        pay = tb.Frame(self); pay.pack(fill="x", padx=12, pady=6)
        tb.Label(pay, text="Pagamento").pack(side="left")
        self.cmb_pay = tb.Combobox(pay, values=["Dinheiro","Crédito","Débito","PIX"], state="readonly"); self.cmb_pay.current(0)
        self.cmb_pay.pack(side="left", padx=8)
        tb.Label(pay, text="Recebido").pack(side="left")
        self.ent_received = tb.Entry(pay, width=14); self.ent_received.insert(0, "0"); self.ent_received.pack(side="left", padx=8)
        self.lbl_subtotal = tb.Label(pay, text="Subtotal: R$ 0,00"); self.lbl_subtotal.pack(side="right", padx=12)
        self.lbl_total = tb.Label(pay, text="TOTAL: R$ 0,00", font=("Segoe UI", 12, "bold"), bootstyle=SUCCESS)
        self.lbl_total.pack(side="right", padx=12)

        btns = tb.Frame(self); btns.pack(fill="x", padx=12, pady=8)
        tb.Button(btns, text="Finalizar Venda (F2)", command=self.finish_sale, bootstyle=PRIMARY).pack(side="left")
        tb.Button(btns, text="Remover item", command=self.remove_selected, bootstyle=SECONDARY).pack(side="left", padx=6)
        tb.Button(btns, text="Limpar carrinho", command=self.clear_cart, bootstyle=SECONDARY).pack(side="left")
        self.bind_all("<F2>", lambda e: self.finish_sale())
        self._recalc()
    def add_by_barcode(self, event=None):
        code = self.ent_barcode.get().strip(); self.ent_barcode.delete(0, tk.END)
        if not code: return
        row = self.product_repo.get_by_barcode(code)
        if not row:
            messagebox.showwarning("Não encontrado", f"Código {code} não cadastrado."); return
        pid, name, price, stock, cost, margin = row
        if stock <= 0:
            if not messagebox.askyesno("Sem estoque", f"{name} está sem estoque. Adicionar mesmo assim?"): return
        for iid in self.cart.get_children():
            vals = self.cart.item(iid, 'values')
            if int(vals[0]) == pid:
                qty = int(vals[2]) + 1; unit_price = to_decimal(vals[3]); line_total = (unit_price * qty).quantize(MONEY_Q)
                self.cart.item(iid, values=(pid, name, qty, f"{unit_price}", f"{line_total}")); self._recalc(); return
        unit_price = to_decimal(price)
        self.cart.insert('', 'end', values=(pid, name, 1, f"{unit_price}", f"{unit_price}")); self._recalc()
    def remove_selected(self):
        for s in self.cart.selection(): self.cart.delete(s); self._recalc()
    def clear_cart(self):
        for iid in self.cart.get_children(): self.cart.delete(iid); self._recalc()
    def _recalc(self):
        subtotal = Decimal('0')
        for iid in self.cart.get_children():
            vals = self.cart.item(iid, 'values'); subtotal += to_decimal(vals[4])
        self.lbl_subtotal.config(text=f"Subtotal: {money(subtotal)}"); self.lbl_total.config(text=f"TOTAL: {money(subtotal)}")
        return subtotal
    def finish_sale(self):
        items = []
        for iid in self.cart.get_children():
            pid, name, qty, unit_price, line_total = self.cart.item(iid, 'values')
            items.append({'product_id': int(pid), 'name': name, 'qty': int(qty),
                          'unit_price': to_decimal(unit_price), 'line_total': to_decimal(line_total)})
        if not items:
            messagebox.showwarning("Vazio", "Carrinho vazio."); return
        subtotal = self._recalc(); payment = self.cmb_pay.get()
        received = to_decimal(self.ent_received.get()) if payment == 'Dinheiro' else Decimal('0')
        discount = Decimal('0'); total = subtotal - discount; change = (received - total) if payment == 'Dinheiro' else Decimal('0')
        if payment == 'Dinheiro' and received < total:
            messagebox.showwarning("Atenção", "Valor recebido menor que o total."); return
        sale_id = self.master.sales_repo.create_sale(user_id=self.master.state['user']['id'], payment_method=payment,
                                                     subtotal=subtotal, discount=discount, total=total, received=received, change_due=change)
        for it in items:
            cur = self.master.product_repo.db.execute("SELECT cost_price, margin_pct FROM products WHERE id=%s", (it['product_id'],))
            cost, margin = cur.fetchone()
            self.master.sales_repo.add_item(sale_id=sale_id, product_id=it['product_id'], qty=it['qty'],
                                            unit_price=it['unit_price'], unit_cost=to_decimal(cost), margin_pct=to_decimal(margin))
            self.master.product_repo.adjust_stock(it['product_id'], -it['qty'])
        cur = self.master.product_repo.db.execute("SELECT id, created_at, payment_method, subtotal, discount, total, received, change_due FROM sales WHERE id=%s", (sale_id,))
        sale_row = cur.fetchone()
        sale = {'id': sale_row[0], 'created_at': sale_row[1], 'payment_method': sale_row[2],
                'subtotal': Decimal(sale_row[3]), 'discount': Decimal(sale_row[4]),
                'total': Decimal(sale_row[5]), 'received': Decimal(sale_row[6]), 'change_due': Decimal(sale_row[7])}
        items_full = [{'name': it['name'], 'qty': it['qty'], 'unit_price': it['unit_price'],
                       'line_total': (it['unit_price'] * it['qty']).quantize(MONEY_Q)} for it in items]
        pix_payload = ""
        if payment == "PIX":
            cur = self.master.product_repo.db.execute("SELECT store_name, pix_key, pix_merchant_city FROM settings WHERE id=1")
            st = cur.fetchone(); store_name = (st[0] or "Minha Adega").upper(); pix_key = st[1] or ""; pix_city = (st[2] or "SAO PAULO").upper().replace(" ", "")
            pix_payload = build_pix_payload(pix_key, store_name, pix_city, amount=total, txid=f"VENDA{sale_id}")
        self.master.printer.print_receipt(sale, items_full, attendant_name=self.master.state['user']['username'], pix_payload=pix_payload)
        messagebox.showinfo("OK", f"Venda {sale_id} concluída. Total: {money(total)}" + (f" | Troco: {money(change)}" if payment=='Dinheiro' else ""))
        self.clear_cart()

class ReportsPage(tb.Frame):
    def __init__(self, master, sales_repo):
        super().__init__(master); self.sales_repo = sales_repo
        filt = tb.Frame(self); filt.pack(fill="x", padx=12, pady=8)
        tb.Label(filt, text="De (AAAA-MM-DD)").pack(side="left")
        self.ent_start = tb.Entry(filt, width=14); self.ent_start.pack(side="left", padx=6)
        tb.Label(filt, text="Até").pack(side="left"); self.ent_end = tb.Entry(filt, width=14); self.ent_end.pack(side="left", padx=6)
        self.cmb_kind = tb.Combobox(filt, values=["Vendas","Lucro","Mais vendidos","Baixo estoque","A vencer (30d)"], state="readonly"); self.cmb_kind.current(0)
        self.cmb_kind.pack(side="left", padx=8)
        tb.Button(filt, text="Gerar", command=self.generate, bootstyle=PRIMARY).pack(side="left", padx=6)
        tb.Button(filt, text="Exportar CSV", command=self.export_csv, bootstyle=INFO).pack(side="left")
        cols = ("c1","c2","c3","c4","c5")
        self.tree = tb.Treeview(self, columns=cols, show="headings", height=18, bootstyle=INFO)
        for i, c in enumerate(cols, start=1): self.tree.heading(c, text=f"Col {i}"); self.tree.column(c, width=200)
        self.tree.pack(fill="both", expand=True, padx=12, pady=12)
    def _get_dates(self):
        s = self.ent_start.get().strip() or date.today().strftime("%Y-%m-01")
        e = self.ent_end.get().strip() or date.today().strftime("%Y-%m-%d")
        try:
            start = datetime.strptime(s, "%Y-%m-%d"); end = datetime.strptime(e, "%Y-%m-%d") + timedelta(days=1, seconds=-1)
        except ValueError:
            messagebox.showerror("Erro", "Datas inválidas. Use AAAA-MM-DD."); return None, None
        return start, end
    def generate(self):
        kind = self.cmb_kind.get()
        for i in self.tree.get_children(): self.tree.delete(i)
        if kind in ("Vendas", "Lucro", "Mais vendidos"):
            start, end = self._get_dates(); 
            if not start: return
            if kind == "Vendas":
                rows = self.sales_repo.report_sales(start, end)
                self.tree.heading("c1", text="ID"); self.tree.heading("c2", text="Data/Hora"); self.tree.heading("c3", text="Pgto")
                self.tree.heading("c4", text="Subtotal"); self.tree.heading("c5", text="Total")
                for r in rows:
                    self.tree.insert('', 'end', values=(r[0], r[1].strftime('%d/%m/%Y %H:%M'), r[2], money(Decimal(r[3])), money(Decimal(r[5]))))
            elif kind == "Lucro":
                rows = self.sales_repo.report_profit(start, end)
                self.tree.heading("c1", text="ID"); self.tree.heading("c2", text="Data/Hora"); self.tree.heading("c3", text="Lucro")
                self.tree.heading("c4", text="-"); self.tree.heading("c5", text="-")
                for r in rows:
                    self.tree.insert('', 'end', values=(r[0], r[1].strftime('%d/%m/%Y %H:%M'), money(Decimal(r[2])), '', ''))
            elif kind == "Mais vendidos":
                rows = self.sales_repo.report_top_products(start, end)
                self.tree.heading("c1", text="Produto"); self.tree.heading("c2", text="Qtd"); self.tree.heading("c3", text="Total")
                self.tree.heading("c4", text="-"); self.tree.heading("c5", text="-")
                for r in rows:
                    self.tree.insert('', 'end', values=(r[0], r[1], money(Decimal(r[2])), '', ''))
        elif kind == "Baixo estoque":
            rows = self.sales_repo.report_low_stock()
            self.tree.heading("c1", text="SKU"); self.tree.heading("c2", text="EAN"); self.tree.heading("c3", text="Produto")
            self.tree.heading("c4", text="Estoque"); self.tree.heading("c5", text="Mínimo")
            for r in rows: self.tree.insert('', 'end', values=r)
        elif kind == "A vencer (30d)":
            rows = self.sales_repo.report_expiring(30)
            self.tree.heading("c1", text="SKU"); self.tree.heading("c2", text="EAN"); self.tree.heading("c3", text="Produto")
            self.tree.heading("c4", text="Validade"); self.tree.heading("c5", text="Estoque")
            for r in rows:
                v = r[3].strftime('%d/%m/%Y') if r[3] else ''
                self.tree.insert('', 'end', values=(r[0], r[1], r[2], v, r[4]))
    def export_csv(self):
        path = filedialog.asksaveasfilename(defaultextension='.csv', filetypes=[('CSV','*.csv')])
        if not path: return
        with open(path, 'w', newline='', encoding='utf-8') as f:
            w = csv.writer(f, delimiter=';')
            heads = [self.tree.heading(c)['text'] for c in self.tree['columns']]
            w.writerow(heads)
            for iid in self.tree.get_children(): w.writerow(self.tree.item(iid, 'values'))
        messagebox.showinfo("OK", f"Arquivo salvo em {path}")

class SuppliersPage(tb.Frame):
    def __init__(self, master, repo):
        super().__init__(master); self.repo = repo
        frm = tb.Labelframe(self, text="Fornecedor", bootstyle=INFO); frm.pack(fill="x", padx=12, pady=12)
        self.var_id = tk.StringVar(); self.var_name = tk.StringVar(); self.var_document = tk.StringVar(); self.var_phone = tk.StringVar(); self.var_email = tk.StringVar()
        grid = [("ID", self.var_id), ("Nome", self.var_name), ("Documento", self.var_document), ("Telefone", self.var_phone), ("E-mail", self.var_email)]
        for i, (lbl, var) in enumerate(grid):
            ttk.Label(frm, text=lbl).grid(row=i//4, column=(i%4)*2, sticky="e", padx=6, pady=4)
            e = ttk.Entry(frm, textvariable=var); e.grid(row=i//4, column=(i%4)*2+1, sticky="we", padx=6, pady=4)
        btns = tb.Frame(frm); btns.grid(row=2, column=0, columnspan=8, sticky="we", pady=8)
        tb.Button(btns, text="Salvar/Atualizar", command=self.save, bootstyle=SUCCESS).pack(side="left", padx=6)
        tb.Button(btns, text="Limpar", command=self.clear, bootstyle=SECONDARY).pack(side="left", padx=6)
        tb.Button(btns, text="Excluir", command=self.delete, bootstyle=DANGER).pack(side="left", padx=6)
        for c in range(8): frm.columnconfigure(c, weight=1)

        searchf = tb.Frame(self); searchf.pack(fill="x", padx=12)
        ttk.Label(searchf, text="Buscar").pack(side="left")
        self.ent_search = tb.Entry(searchf, width=30); self.ent_search.pack(side="left", padx=6)
        tb.Button(searchf, text="OK", command=self.refresh, bootstyle=PRIMARY).pack(side="left", padx=6)

        cols = ("id", "name", "document", "phone", "email", "created_at")
        self.tree = tb.Treeview(self, columns=cols, show="headings", height=12, bootstyle=INFO)
        for c in cols: self.tree.heading(c, text=c); self.tree.column(c, width=160)
        self.tree.pack(fill="both", expand=True, padx=12, pady=12)
        self.tree.bind("<<TreeviewSelect>>", self.on_select)
        self.refresh()
    def save(self):
        try:
            data = {"id": self.var_id.get().strip() or None, "name": self.var_name.get().strip(),
                    "document": self.var_document.get().strip(), "phone": self.var_phone.get().strip(), "email": self.var_email.get().strip()}
            self.repo.upsert(data); messagebox.showinfo("OK", "Fornecedor salvo/atualizado."); self.refresh(); self.clear()
        except Exception as e:
            messagebox.showerror("Erro", f"Falha ao salvar: {e}")
    def clear(self):
        self.var_id.set(""); self.var_name.set(""); self.var_document.set(""); self.var_phone.set(""); self.var_email.set("")
    def delete(self):
        sel = self.tree.selection(); 
        if not sel: return
        iid = sel[0]; sid = int(self.tree.item(iid, 'values')[0])
        if messagebox.askyesno("Confirmar", "Excluir fornecedor selecionado? (Produtos ficarão sem fornecedor)"):
            self.repo.delete(sid); self.refresh(); self.clear()
    def refresh(self):
        term = self.ent_search.get().strip(); rows = self.repo.list_all(term)
        for i in self.tree.get_children(): self.tree.delete(i)
        for r in rows: self.tree.insert('', 'end', values=r)
    def on_select(self, event):
        sel = self.tree.selection(); 
        if not sel: return
        vals = self.tree.item(sel[0], 'values')
        self.var_id.set(vals[0]); self.var_name.set(vals[1]); self.var_document.set(vals[2]); self.var_phone.set(vals[3]); self.var_email.set(vals[4])

class SettingsPage(tb.Frame):
    def __init__(self, master, db: DB, printer: ReceiptPrinter, state: dict):
        super().__init__(master); self.db = db; self.printer = printer; self.state = state
        self.vars = {}
        cur = self.db.execute("SELECT * FROM settings WHERE id=1"); row = cur.fetchone(); cols = [d[0] for d in cur.description]
        data = dict(zip(cols, row)) if row else DEFAULT_SETTINGS
        for k, v in DEFAULT_SETTINGS.items():
            self.vars[k] = tk.StringVar(value=str(data.get(k, v)))
        form = tb.Frame(self); form.pack(fill="x", padx=12, pady=12)

        def row(label, key, col):
            ttk.Label(form, text=label).grid(row=row.i, column=col*2, sticky='e', padx=6, pady=4)
            ttk.Entry(form, textvariable=self.vars[key]).grid(row=row.i, column=col*2+1, sticky='we', padx=6, pady=4)
            if col==3: row.i += 1
        row.i = 0

        tb.Label(form, text="Dados da Loja", font=("Segoe UI", 11, 'bold'), bootstyle=(SECONDARY)).grid(row=row.i, column=0, sticky='w', pady=(0,6)); row.i += 1
        row("Nome Fantasia", 'store_name', 0); row("Documento (CNPJ)", 'store_document', 1); row("Endereço", 'store_address', 2); row("Telefone", 'store_phone', 3)
        row("Rodapé recibo", 'receipt_footer', 0)

        tb.Label(form, text="PIX", font=("Segoe UI", 11, 'bold'), bootstyle=(SECONDARY)).grid(row=row.i, column=0, sticky='w', pady=(10,6)); row.i += 1
        row("Chave PIX", 'pix_key', 0); row("Cidade (p/ QR)", 'pix_merchant_city', 1)

        tb.Label(form, text="Impressora ESC/POS", font=("Segoe UI", 11, 'bold'), bootstyle=(SECONDARY)).grid(row=row.i, column=0, sticky='w', pady=(10,6)); row.i += 1
        row("Habilitar (0/1)", 'print_enabled', 0); row("Tipo (USB/Serial/Network)", 'printer_kind', 1); row("USB Vendor ID (hex)", 'usb_vendor_id', 2); row("USB Product ID (hex)", 'usb_product_id', 3)
        row("USB IN EP (opcional)", 'usb_in_ep', 0); row("USB OUT EP (opcional)", 'usb_out_ep', 1); row("Serial COM", 'serial_device', 2); row("Serial baud", 'serial_baud', 3)
        row("Host IP", 'network_host', 0); row("Host Porta", 'network_port', 1)

        for c in range(8): form.columnconfigure(c, weight=1)
        tb.Button(self, text="Salvar configurações", command=self.save, bootstyle=SUCCESS).pack(pady=10)
    def save(self):
        values = {k: v.get() for k, v in self.vars.items()}; cols = list(values.keys())
        self.db.execute(f"REPLACE INTO settings ({','.join(cols)}) VALUES ({','.join(['%s']*len(cols))})", tuple(values[c] for c in cols))
        self.db.commit(); messagebox.showinfo("OK", "Configurações salvas."); self.printer._load()

class UsersPage(tb.Frame):
    def __init__(self, master, user_repo, current_user_id: int):
        super().__init__(master); self.repo = user_repo; self.current_user_id = current_user_id
        frm = tb.Labelframe(self, text="Novo usuário", bootstyle=INFO); frm.pack(fill="x", padx=12, pady=12)
        self.var_username = tk.StringVar(); self.var_role = tk.StringVar(value="caixa"); self.var_pass1 = tk.StringVar(); self.var_pass2 = tk.StringVar()
        ttk.Label(frm, text="Usuário").grid(row=0, column=0, sticky="e", padx=6, pady=4); ttk.Entry(frm, textvariable=self.var_username, width=24).grid(row=0, column=1, sticky="w")
        ttk.Label(frm, text="Cargo").grid(row=0, column=2, sticky="e", padx=6, pady=4); tb.Combobox(frm, textvariable=self.var_role, values=["admin","gerente","caixa"], state="readonly", width=12).grid(row=0, column=3, sticky="w")
        ttk.Label(frm, text="Senha").grid(row=1, column=0, sticky="e", padx=6, pady=4); ttk.Entry(frm, textvariable=self.var_pass1, show="*", width=24).grid(row=1, column=1, sticky="w")
        ttk.Label(frm, text="Confirmar").grid(row=1, column=2, sticky="e", padx=6, pady=4); ttk.Entry(frm, textvariable=self.var_pass2, show="*", width=24).grid(row=1, column=3, sticky="w")
        tb.Button(frm, text="Criar", command=self.create_user, bootstyle=SUCCESS).grid(row=0, column=4, rowspan=2, padx=10)
        cols = ("id","username","role","created_at")
        self.tree = tb.Treeview(self, columns=cols, show="headings", height=14, bootstyle=INFO)
        for c in cols: self.tree.heading(c, text=c); self.tree.column(c, width=180)
        self.tree.pack(fill="both", expand=True, padx=12, pady=12)
        btns = tb.Frame(self); btns.pack(fill="x", padx=12, pady=8)
        tb.Button(btns, text="Resetar senha", command=self.reset_password, bootstyle=SECONDARY).pack(side="left")
        tb.Button(btns, text="Mudar cargo", command=self.change_role, bootstyle=SECONDARY).pack(side="left", padx=6)
        tb.Button(btns, text="Excluir", command=self.delete_user, bootstyle=DANGER).pack(side="left")
        self.refresh()
    def refresh(self):
        for i in self.tree.get_children(): self.tree.delete(i)
        for r in self.repo.list_all(): self.tree.insert('', 'end', values=r)
    def create_user(self):
        u = self.var_username.get().strip(); r = self.var_role.get().strip(); p1 = self.var_pass1.get(); p2 = self.var_pass2.get()
        if not u or not p1: messagebox.showwarning("Atenção", "Usuário e senha são obrigatórios."); return
        if p1 != p2: messagebox.showerror("Erro", "Senhas não coincidem."); return
        try:
            self.repo.create_user(u, p1, r); self.var_username.set(""); self.var_pass1.set(""); self.var_pass2.set(""); self.refresh(); messagebox.showinfo("OK", "Usuário criado.")
        except Exception as e: messagebox.showerror("Erro", f"Falha ao criar usuário: {e}")
    def _selected_user_id(self):
        sel = self.tree.selection(); 
        if not sel: return None
        return int(self.tree.item(sel[0], 'values')[0])
    def reset_password(self):
        uid = self._selected_user_id(); 
        if not uid: return
        if uid == self.master.state['user']['id'] and not messagebox.askyesno("Confirmar", "Resetar a própria senha?"): return
        newp = simpledialog.askstring("Resetar senha", "Nova senha:", show="*"); 
        if not newp: return
        self.repo.set_password(uid, newp); messagebox.showinfo("OK", "Senha resetada.")
    def change_role(self):
        uid = self._selected_user_id(); 
        if not uid: return
        role = simpledialog.askstring("Cargo", "Digite cargo (admin/gerente/caixa):"); 
        if not role or role not in ("admin","gerente","caixa"): messagebox.showerror("Erro", "Cargo inválido."); return
        self.repo.set_role(uid, role); self.refresh()
    def delete_user(self):
        uid = self._selected_user_id(); 
        if not uid: return
        if uid == self.master.state['user']['id']:
            messagebox.showerror("Erro", "Não é possível excluir o usuário logado."); return
        if messagebox.askyesno("Confirmar", "Excluir usuário selecionado?"):
            try: self.repo.delete_user(uid); self.refresh()
            except Exception as e: messagebox.showerror("Erro", f"Falha ao excluir: {e}")

# ===================== LOGIN =====================
class LoginWindow(tb.Toplevel):
    def __init__(self, master, db: DB, on_success):
        super().__init__(master)
        self.db = db; self.on_success = on_success
        self.title("Adega PDV - Login"); self.geometry("340x230"); self.resizable(False, False); self.grab_set()
        frame = tb.Frame(self, padding=20); frame.pack(fill="both", expand=True)
        title = tb.Label(frame, text="🍷 Adega PDV", font=("Segoe UI", 16, "bold")); title.pack(pady=(0,8))
        tb.Label(frame, text="Usuário").pack(anchor="w"); self.ent_user = tb.Entry(frame); self.ent_user.pack(fill="x"); self.ent_user.focus_set()
        tb.Label(frame, text="Senha").pack(anchor="w", pady=(8,0)); self.ent_pass = tb.Entry(frame, show="*"); self.ent_pass.pack(fill="x")
        self.var_show = tk.BooleanVar(value=False)
        tb.Checkbutton(frame, text="Mostrar senha", variable=self.var_show, command=self._toggle_pass, bootstyle=SECONDARY).pack(anchor="w", pady=6)
        tb.Button(frame, text="Entrar", command=self.try_login, bootstyle=PRIMARY).pack(fill="x", pady=6)
        self.bind("<Return>", lambda e: self.try_login())
    def _toggle_pass(self):
        self.ent_pass.config(show="" if self.var_show.get() else "*")
    def try_login(self):
        username = self.ent_user.get().strip(); password = self.ent_pass.get()
        repo = UserRepo(self.db); row = repo.get_by_username(username)
        if row and verify_password(password, row[2]):
            self.destroy(); self.on_success({"id": row[0], "username": row[1], "role": row[3]})
        else:
            messagebox.showerror("Erro", "Usuário ou senha inválidos.")

# ===================== APLICAÇÃO PRINCIPAL =====================
class AdegaApp(tb.Window):
    def __init__(self):
        super().__init__(themename="darkly")
        self.title("Adega PDV"); self.geometry("1280x800")
        self.state = {"user": None}

        # Estilos adicionais
        style = self.style
        style.configure("Wine.TFrame", background=WINE_DARK)
        style.configure("WineTop.TFrame", background=WINE)
        style.configure("WineTitle.TLabel", font=("Segoe UI", 14, "bold"), foreground="white", background=WINE)
        style.configure("WineUser.TLabel", font=("Segoe UI", 10), foreground="#f0dfe5", background=WINE)
        style.configure("Sidebar.TButton", font=("Segoe UI", 11), padding=10)
        style.configure("Status.TLabel", font=("Segoe UI", 9))

        # Conexão DB
        self.db = DB(DB_CONFIG); self.db.connect(); init_database(self.db)
        self.user_repo = UserRepo(self.db); self.product_repo = ProductRepo(self.db); self.sales_repo = SalesRepo(self.db); self.supplier_repo = SupplierRepo(self.db); self.printer = ReceiptPrinter(self.db)

        # Login
        self.wait_visibility(); LoginWindow(self, self.db, on_success=self._after_login)

    # --- Layout ---
    def _after_login(self, user):
        self.state["user"] = user
        self._build_shell()
        self.show_page("PDV")  # abre no caixa

    def _build_shell(self):
        # Topbar
        top = ttk.Frame(self, style="WineTop.TFrame"); top.pack(fill="x", side="top")
        ttk.Label(top, text="🍷 Adega PDV", style="WineTitle.TLabel").pack(side="left", padx=12, pady=10)
        ttk.Label(top, text=f"Usuário: {self.state['user']['username']} ({self.state['user']['role']})", style="WineUser.TLabel").pack(side="right", padx=12)
        tb.Button(top, text="Trocar senha", command=self.change_password_dialog, bootstyle=SECONDARY).pack(side="right", padx=8, pady=8)
        tb.Button(top, text="Sair", command=self.destroy, bootstyle=DANGER).pack(side="right", padx=8, pady=8)

        # Main area
        main = ttk.Frame(self); main.pack(fill="both", expand=True)
        # Sidebar
        self.sidebar = tb.Frame(main, padding=8, bootstyle=SECONDARY)
        self.sidebar.pack(side="left", fill="y")
        self._nav_buttons = {}
        self._make_nav_button("PDV", "🧾 PDV", row=0, style=SUCCESS)
        self._make_nav_button("Produtos", "🏷️ Produtos", row=1)
        self._make_nav_button("Relatórios", "📊 Relatórios", row=2)
        self._make_nav_button("Fornecedores", "📦 Fornecedores", row=3)
        self._make_nav_button("Configurações", "⚙️ Configurações", row=4)
        if self.state["user"]["role"] == "admin":
            self._make_nav_button("Usuários", "👤 Usuários", row=5, style=WARNING)

        # Container de páginas
        self.container = tb.Frame(main, padding=6)
        self.container.pack(side="left", fill="both", expand=True)

        # Páginas
        self.pages = {}
        self.pages["Produtos"] = ProductPage(self.container, self.product_repo)
        self.pages["PDV"] = PosPage(self.container, self.product_repo, self.sales_repo, self.printer, self.state)
        self.pages["Relatórios"] = ReportsPage(self.container, self.sales_repo)
        self.pages["Fornecedores"] = SuppliersPage(self.container, self.supplier_repo)
        self.pages["Configurações"] = SettingsPage(self.container, self.db, self.printer, self.state)
        if self.state["user"]["role"] == "admin":
            self.pages["Usuários"] = UsersPage(self.container, self.user_repo, current_user_id=self.state["user"]["id"])

        # Status bar
        self.status = ttk.Frame(self, padding=6)
        self.status.pack(fill="x", side="bottom")
        self.lbl_status = ttk.Label(self.status, text="Pronto", style="Status.TLabel")
        self.lbl_status.pack(side="left")
        self.lbl_clock = ttk.Label(self.status, text="", style="Status.TLabel")
        self.lbl_clock.pack(side="right")
        self._tick_clock()

    def _make_nav_button(self, key, text, row, style=PRIMARY):
        btn = tb.Button(self.sidebar, text=text, bootstyle=style, command=lambda k=key: self.show_page(k))
        btn.grid(row=row, column=0, sticky="we", pady=4)
        self._nav_buttons[key] = btn

    def _tick_clock(self):
        now = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
        self.lbl_clock.config(text=now)
        self.after(1000, self._tick_clock)

    def show_page(self, key):
        # destiva botões
        for k, b in self._nav_buttons.items():
            b.configure(bootstyle=SECONDARY if k != key else SUCCESS)
        # troca página
        for name, frame in self.pages.items():
            frame.pack_forget()
        page = self.pages[key]
        page.pack(fill="both", expand=True)
        self.lbl_status.config(text=f"Abrindo: {key}")

    def change_password_dialog(self):
        current = simpledialog.askstring("Senha atual", "Digite sua senha atual:", parent=self, show="*")
        if not current: return
        row = self.user_repo.get_by_username(self.state["user"]["username"])
        if not row or not verify_password(current, row[2]): messagebox.showerror("Erro", "Senha atual incorreta."); return
        new1 = simpledialog.askstring("Nova senha", "Digite a nova senha:", parent=self, show="*"); 
        if not new1: return
        new2 = simpledialog.askstring("Confirme", "Repita a nova senha:", parent=self, show="*")
        if new1 != new2: messagebox.showerror("Erro", "As senhas não coincidem."); return
        self.user_repo.set_password(self.state["user"]["id"], new1); messagebox.showinfo("OK", "Senha alterada com sucesso.")

# ===================== MAIN =====================
if __name__ == "__main__":
    try:
        app = AdegaApp()
        app.mainloop()
    except mysql.connector.Error as e:
        try:
            messagebox.showerror("Erro MySQL", str(e))
        except Exception:
            print("Erro MySQL:", e)
    except Exception as e:
        print("Erro fatal:", e)
