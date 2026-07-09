resource "azurerm_static_web_app" "frontend" {
  name                = "${var.project_name}-${var.environment}-frontend"
  resource_group_name = azurerm_resource_group.rg.name
  location            = "eastasia" # SWA has limited regional availability for the Free tier
  sku_tier            = "Free"
  sku_size            = "Free"

  tags = azurerm_resource_group.rg.tags
}
