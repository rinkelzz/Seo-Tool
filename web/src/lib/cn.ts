import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

/** Combine conditional class names and merge conflicting Tailwind utilities. */
export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}
