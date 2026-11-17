import { OG_SIZE, ogImage } from "@/lib/og";

export const size = OG_SIZE;
export const contentType = "image/png";
export const alt = "Provenance Risk: supplier and counterparty risk intelligence";

export default function Image() {
  return ogImage(
    "See every risk behind every supplier, under every name.",
    "Supplier and counterparty risk intelligence",
  );
}
