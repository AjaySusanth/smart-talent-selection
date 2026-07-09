resource "random_password" "db_password" {
  length  = 24
  special = false
}

resource "azurerm_postgresql_flexible_server" "db" {
  name                   = "${var.project_name}-${var.environment}-pg"
  resource_group_name    = azurerm_resource_group.rg.name
  location               = azurerm_resource_group.rg.location
  version                = "16"
  administrator_login    = "talentadmin"
  administrator_password = random_password.db_password.result

  storage_mb   = 32768
  sku_name     = "B_Standard_B1ms" # Burstable SKU suitable for development/staging
  zone         = "1"

  lifecycle {
    ignore_changes = [
      zone,
      high_availability[0].standby_availability_zone
    ]
  }

  tags = azurerm_resource_group.rg.tags
}

# Register the vector extension so the app can run "CREATE EXTENSION vector;"
resource "azurerm_postgresql_flexible_server_configuration" "extensions" {
  name      = "azure.extensions"
  server_id = azurerm_postgresql_flexible_server.db.id
  value     = "vector"
}

# Allow Azure Internal Services to connect to Postgres
resource "azurerm_postgresql_flexible_server_firewall_rule" "allow_azure" {
  name             = "allow-azure-services"
  server_id        = azurerm_postgresql_flexible_server.db.id
  start_ip_address = "0.0.0.0"
  end_ip_address   = "0.0.0.0"
}

resource "azurerm_postgresql_flexible_server_database" "db_name" {
  name      = "talent_engine"
  server_id = azurerm_postgresql_flexible_server.db.id
  collation = "en_US.utf8"
  charset   = "utf8"
}
