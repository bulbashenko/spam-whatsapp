// @/pages/login.tsx

"use client";

import React, { FormEvent, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { signIn } from "next-auth/react";
import { useRouter } from "next/navigation";
import { useToast } from "@/hooks/use-toast";
import { Card } from "@/components/ui/card";
import { motion } from "motion/react";
import { Mail, Lock, Eye, EyeOff, LogIn, Facebook } from "lucide-react";
import Link from "next/link";

export default function LoginPage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const router = useRouter();
  const { toast } = useToast();

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError("");

    const res = await signIn("credentials", {
      email,
      password,
      redirect: false,
    });

    if (res?.error) {
      setError(res.error);
      toast({
        title: "Login Error",
        description: res.error,
        variant: "destructive",
      });
    } else {
      toast({
        title: "Login Successful",
        description: "You have successfully logged in.",
      });
      router.push("/dashboard/sender");
    }
  }

  return (
    <div className="flex items-center justify-center min-h-screen bg-gray-100 dark:bg-gray-900 p-4">
      <motion.div
        initial={{ opacity: 0, scale: 0.95 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={{ duration: 0.3 }}
        className="w-full max-w-sm"
      >
        <Card className="p-8 shadow-lg bg-white dark:bg-gray-800">
          <form onSubmit={handleSubmit} className="space-y-6">
            <div className="flex flex-col items-center mb-4">
              <Mail className="w-12 h-12 text-indigo-600 dark:text-indigo-400 mb-2" />
              <h1 className="text-2xl font-bold text-gray-800 dark:text-gray-200">
                Login
              </h1>
            </div>
            {error && <p className="text-red-500 text-center">{error}</p>}
            <div className="relative">
              <Input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="example@mail.com"
                required
                className="pl-10"
              />
              <Mail className="absolute left-3 top-1/2 transform -translate-y-1/2 text-gray-400" />
            </div>
            <div className="relative">
              <Input
                type={showPassword ? "text" : "password"}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••••"
                required
                className="pl-10 pr-10"
              />
              <Lock className="absolute left-3 top-1/2 transform -translate-y-1/2 text-gray-400" />
              <button
                type="button"
                onClick={() => setShowPassword(!showPassword)}
                className="absolute right-3 top-1/2 transform -translate-y-1/2 text-gray-400 hover:text-gray-600 dark:hover:text-gray-200 focus:outline-none"
                aria-label={showPassword ? "Hide password" : "Show password"}
              >
                {showPassword ? (
                  <EyeOff className="w-5 h-5" />
                ) : (
                  <Eye className="w-5 h-5" />
                )}
              </button>
            </div>
            {/* Login button using email/password */}
            <Button
              type="submit"
              className="w-full flex items-center justify-center space-x-2"
            >
              <LogIn className="w-5 h-5" />
              <span>Log In</span>
            </Button>

            {/* Facebook login button */}
            <Button
              type="button"
              onClick={() => signIn("facebook")} // Trigger the 'facebook' provider
              variant="outline"
              className="w-full flex items-center justify-center space-x-2"
            >
              <Facebook className="w-5 h-5" />
              <span>Log In with Facebook</span>
            </Button>
          </form>
          <div className="mt-6 text-center space-y-4">
            <p className="text-sm text-gray-600">
              Don&apos;t have an account?{" "}
              <Link
                href="/register"
                className="text-indigo-600 hover:underline"
              >
                Register
              </Link>
            </p>
          </div>
        </Card>
      </motion.div>
    </div>
  );
}
