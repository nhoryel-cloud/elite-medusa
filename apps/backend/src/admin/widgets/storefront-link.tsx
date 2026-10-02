import { defineWidgetConfig } from "@medusajs/admin-sdk"
import { Button, Container, Heading, Text } from "@medusajs/ui"

/**
 * Storefront URL. The admin UI is bundled for the browser, so this is a plain
 * constant — update it when the storefront moves hosts (e.g. production).
 */
const STOREFRONT_URL = "http://localhost:3000"

type ProductData = {
  id?: string
  handle?: string
}

/**
 * "View in storefront" widget on the product details page — opens this
 * product's single page on the Next.js storefront in a new tab.
 */
const StorefrontLink = ({ data }: { data?: ProductData }) => {
  const href = data?.handle
    ? `${STOREFRONT_URL.replace(/\/+$/, "")}/shop/${data.handle}`
    : `${STOREFRONT_URL.replace(/\/+$/, "")}/shop`

  return (
    <Container className="flex flex-wrap items-center justify-between gap-3">
      <div>
        <Heading level="h3">Storefront</Heading>
        <Text size="small" className="text-ui-fg-subtle">
          Open this product&apos;s single page on the storefront.
        </Text>
      </div>
      <a href={href} rel="noopener noreferrer" target="_blank">
        <Button type="button" variant="secondary">
          View in storefront ↗
        </Button>
      </a>
    </Container>
  )
}

export const config = defineWidgetConfig({
  zone: "product.details.before",
  id: "storefront-link",
})

export default StorefrontLink
