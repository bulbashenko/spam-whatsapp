// app/page.tsx
import { redirect } from "next/navigation";

export default function Home() {
  // Просто сразу уходим на login
  redirect("/login");
}
