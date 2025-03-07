// app/(auth)/layout.tsx
import { ReactNode } from "react";
import { getServerSession } from "next-auth/next";
import { authOptions } from "../api/auth/[...nextauth]/authOptions";
import { redirect } from "next/navigation";

export default async function AuthLayout({
  children,
}: {
  children: ReactNode;
}) {
  const session = await getServerSession(authOptions);

  if (session) {
    // Если юзер уже залогинился → на дашборд
    redirect("/dashboard/sender");
  }

  // Если не залогинен — показываем страницы (login или register)
  return <div>{children}</div>;
}
