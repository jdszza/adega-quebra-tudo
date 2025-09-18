-- --------------------------------------------------------
-- Servidor:                     127.0.0.1
-- Versão do servidor:           8.0.30 - MySQL Community Server - GPL
-- OS do Servidor:               Win64
-- HeidiSQL Versão:              12.1.0.6537
-- --------------------------------------------------------

/*!40101 SET @OLD_CHARACTER_SET_CLIENT=@@CHARACTER_SET_CLIENT */;
/*!40101 SET NAMES utf8 */;
/*!50503 SET NAMES utf8mb4 */;
/*!40103 SET @OLD_TIME_ZONE=@@TIME_ZONE */;
/*!40103 SET TIME_ZONE='+00:00' */;
/*!40014 SET @OLD_FOREIGN_KEY_CHECKS=@@FOREIGN_KEY_CHECKS, FOREIGN_KEY_CHECKS=0 */;
/*!40101 SET @OLD_SQL_MODE=@@SQL_MODE, SQL_MODE='NO_AUTO_VALUE_ON_ZERO' */;
/*!40111 SET @OLD_SQL_NOTES=@@SQL_NOTES, SQL_NOTES=0 */;


-- Copiando estrutura do banco de dados para adega_pdv
CREATE DATABASE IF NOT EXISTS `adega_pdv` /*!40100 DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci */ /*!80016 DEFAULT ENCRYPTION='N' */;
USE `adega_pdv`;

-- Copiando estrutura para tabela adega_pdv.products
CREATE TABLE IF NOT EXISTS `products` (
  `id` int NOT NULL AUTO_INCREMENT,
  `sku` varchar(40) NOT NULL,
  `barcode` varchar(32) DEFAULT NULL,
  `name` varchar(180) NOT NULL,
  `item_type` enum('Vinho','Cerveja','Destilado','Outros') NOT NULL DEFAULT 'Outros',
  `category` varchar(80) DEFAULT NULL,
  `brand` varchar(120) DEFAULT NULL,
  `varietal` varchar(120) DEFAULT NULL,
  `vintage` year DEFAULT NULL,
  `volume_ml` int DEFAULT NULL,
  `abv` decimal(5,2) DEFAULT NULL,
  `country` varchar(80) DEFAULT NULL,
  `region` varchar(120) DEFAULT NULL,
  `supplier_id` int DEFAULT NULL,
  `cost_price` decimal(10,2) NOT NULL DEFAULT '0.00',
  `margin_pct` decimal(6,2) NOT NULL DEFAULT '0.00',
  `sale_price` decimal(10,2) NOT NULL DEFAULT '0.00',
  `stock_qty` int NOT NULL DEFAULT '0',
  `min_stock` int NOT NULL DEFAULT '0',
  `lot_code` varchar(60) DEFAULT NULL,
  `expiry` date DEFAULT NULL,
  `active` tinyint(1) NOT NULL DEFAULT '1',
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NULL DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `sku` (`sku`),
  UNIQUE KEY `barcode` (`barcode`),
  KEY `fk_products_supplier` (`supplier_id`),
  CONSTRAINT `fk_products_supplier` FOREIGN KEY (`supplier_id`) REFERENCES `suppliers` (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=3 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- Copiando dados para a tabela adega_pdv.products: ~1 rows (aproximadamente)
INSERT IGNORE INTO `products` (`id`, `sku`, `barcode`, `name`, `item_type`, `category`, `brand`, `varietal`, `vintage`, `volume_ml`, `abv`, `country`, `region`, `supplier_id`, `cost_price`, `margin_pct`, `sale_price`, `stock_qty`, `min_stock`, `lot_code`, `expiry`, `active`, `created_at`, `updated_at`) VALUES
	(1, '01', '01', 'Seda Solta', 'Outros', 'Fumo', 'Zomo', '', NULL, NULL, 0.00, 'Brasil', '', NULL, 0.00, 0.00, 0.50, 97, 33, '', NULL, 1, '2025-09-13 01:32:49', '2025-09-15 00:22:10'),
	(2, '02', '02', 'Cigarro Solto (Eight)', 'Outros', 'Fumo', 'Eight', '', NULL, NULL, 0.00, '', '', NULL, 0.00, 0.00, 0.50, 38, 20, '', NULL, 1, '2025-09-14 20:26:56', '2025-09-15 00:09:29');

-- Copiando estrutura para tabela adega_pdv.sales
CREATE TABLE IF NOT EXISTS `sales` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  `user_id` int NOT NULL,
  `payment_method` enum('Dinheiro','Crédito','Débito','PIX') NOT NULL,
  `subtotal` decimal(10,2) NOT NULL DEFAULT '0.00',
  `discount` decimal(10,2) NOT NULL DEFAULT '0.00',
  `total` decimal(10,2) NOT NULL DEFAULT '0.00',
  `received` decimal(10,2) NOT NULL DEFAULT '0.00',
  `change_due` decimal(10,2) NOT NULL DEFAULT '0.00',
  PRIMARY KEY (`id`),
  KEY `fk_sales_user` (`user_id`),
  CONSTRAINT `fk_sales_user` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=7 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- Copiando dados para a tabela adega_pdv.sales: ~4 rows (aproximadamente)
INSERT IGNORE INTO `sales` (`id`, `created_at`, `user_id`, `payment_method`, `subtotal`, `discount`, `total`, `received`, `change_due`) VALUES
	(3, '2025-09-14 21:00:55', 1, 'Dinheiro', 1.00, 0.00, 1.00, 1.00, 0.00),
	(4, '2025-09-14 23:32:52', 1, 'Dinheiro', 25.00, 0.00, 25.00, 25.00, 0.00),
	(5, '2025-09-15 00:09:29', 1, 'Crédito', 5.00, 0.00, 5.00, 0.00, 0.00),
	(6, '2025-09-15 00:22:10', 1, 'Dinheiro', 1.00, 0.00, 1.00, 5.00, 4.00);

-- Copiando estrutura para tabela adega_pdv.sale_items
CREATE TABLE IF NOT EXISTS `sale_items` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `sale_id` bigint NOT NULL,
  `product_id` int NOT NULL,
  `qty` int NOT NULL,
  `unit_price` decimal(10,2) NOT NULL,
  `unit_cost` decimal(10,2) NOT NULL,
  `margin_pct` decimal(6,2) NOT NULL DEFAULT '0.00',
  `line_total` decimal(10,2) NOT NULL,
  `line_profit` decimal(10,2) NOT NULL,
  PRIMARY KEY (`id`),
  KEY `fk_items_sale` (`sale_id`),
  KEY `fk_items_product` (`product_id`),
  CONSTRAINT `fk_items_product` FOREIGN KEY (`product_id`) REFERENCES `products` (`id`),
  CONSTRAINT `fk_items_sale` FOREIGN KEY (`sale_id`) REFERENCES `sales` (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=7 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- Copiando dados para a tabela adega_pdv.sale_items: ~4 rows (aproximadamente)
INSERT IGNORE INTO `sale_items` (`id`, `sale_id`, `product_id`, `qty`, `unit_price`, `unit_cost`, `margin_pct`, `line_total`, `line_profit`) VALUES
	(3, 3, 2, 2, 0.50, 0.00, 0.00, 1.00, 1.00),
	(4, 4, 2, 50, 0.50, 0.00, 0.00, 25.00, 25.00),
	(5, 5, 2, 10, 0.50, 0.00, 0.00, 5.00, 5.00),
	(6, 6, 1, 2, 0.50, 0.00, 0.00, 1.00, 1.00);

-- Copiando estrutura para tabela adega_pdv.settings
CREATE TABLE IF NOT EXISTS `settings` (
  `id` tinyint NOT NULL,
  `store_name` varchar(120) NOT NULL,
  `store_document` varchar(40) DEFAULT NULL,
  `store_address` varchar(200) DEFAULT NULL,
  `store_phone` varchar(60) DEFAULT NULL,
  `receipt_footer` varchar(240) DEFAULT NULL,
  `print_enabled` tinyint(1) NOT NULL DEFAULT '0',
  `printer_kind` enum('USB','Serial','Network') DEFAULT 'USB',
  `usb_vendor_id` varchar(8) DEFAULT NULL,
  `usb_product_id` varchar(8) DEFAULT NULL,
  `usb_in_ep` varchar(8) DEFAULT NULL,
  `usb_out_ep` varchar(8) DEFAULT NULL,
  `serial_device` varchar(120) DEFAULT NULL,
  `serial_baud` int DEFAULT NULL,
  `network_host` varchar(120) DEFAULT NULL,
  `network_port` int DEFAULT NULL,
  `pix_key` varchar(140) DEFAULT NULL,
  `pix_merchant_city` varchar(60) DEFAULT NULL,
  `brand_primary` varchar(9) DEFAULT NULL,
  `brand_secondary` varchar(9) DEFAULT NULL,
  `brand_bg` varchar(9) DEFAULT NULL,
  `brand_sidebar` varchar(9) DEFAULT NULL,
  `logo_path` varchar(200) DEFAULT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- Copiando dados para a tabela adega_pdv.settings: ~1 rows (aproximadamente)
INSERT IGNORE INTO `settings` (`id`, `store_name`, `store_document`, `store_address`, `store_phone`, `receipt_footer`, `print_enabled`, `printer_kind`, `usb_vendor_id`, `usb_product_id`, `usb_in_ep`, `usb_out_ep`, `serial_device`, `serial_baud`, `network_host`, `network_port`, `pix_key`, `pix_merchant_city`, `brand_primary`, `brand_secondary`, `brand_bg`, `brand_sidebar`, `logo_path`) VALUES
	(1, 'Adega Quebra-Tudo', '', '', '', 'SEM VALOR FISCAL', 0, 'USB', '', '', '', '', '', 9600, '', 9100, 'None', 'None', NULL, NULL, NULL, NULL, NULL);

-- Copiando estrutura para tabela adega_pdv.suppliers
CREATE TABLE IF NOT EXISTS `suppliers` (
  `id` int NOT NULL AUTO_INCREMENT,
  `name` varchar(120) NOT NULL,
  `document` varchar(40) DEFAULT NULL,
  `phone` varchar(40) DEFAULT NULL,
  `email` varchar(120) DEFAULT NULL,
  `created_at` timestamp NULL DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_suppliers_name` (`name`)
) ENGINE=InnoDB AUTO_INCREMENT=2 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- Copiando dados para a tabela adega_pdv.suppliers: ~1 rows (aproximadamente)
INSERT IGNORE INTO `suppliers` (`id`, `name`, `document`, `phone`, `email`, `created_at`) VALUES
	(1, 'Point do Nargas', NULL, NULL, NULL, NULL);

-- Copiando estrutura para tabela adega_pdv.users
CREATE TABLE IF NOT EXISTS `users` (
  `id` int NOT NULL AUTO_INCREMENT,
  `username` varchar(50) NOT NULL,
  `password_hash` varchar(255) NOT NULL,
  `role` enum('admin','gerente','caixa') NOT NULL DEFAULT 'caixa',
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `username` (`username`)
) ENGINE=InnoDB AUTO_INCREMENT=2 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- Copiando dados para a tabela adega_pdv.users: ~0 rows (aproximadamente)
INSERT IGNORE INTO `users` (`id`, `username`, `password_hash`, `role`, `created_at`) VALUES
	(1, 'admin', '0275d8a5284e01223e3c8bda31c1e0ad:58e213c29b4ced1032c3f09b40a2414a6b0db1570e38cdb4cc84d26dcd0d7c38', 'admin', '2025-09-13 01:07:07');

/*!40103 SET TIME_ZONE=IFNULL(@OLD_TIME_ZONE, 'system') */;
/*!40101 SET SQL_MODE=IFNULL(@OLD_SQL_MODE, '') */;
/*!40014 SET FOREIGN_KEY_CHECKS=IFNULL(@OLD_FOREIGN_KEY_CHECKS, 1) */;
/*!40101 SET CHARACTER_SET_CLIENT=@OLD_CHARACTER_SET_CLIENT */;
/*!40111 SET SQL_NOTES=IFNULL(@OLD_SQL_NOTES, 1) */;
