"use client";

import React, { useState } from "react";
import { useSession } from "next-auth/react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { sendEmail, sendWhatsApp } from "@/app/api/services/communications";
import { useToast } from "@/hooks/use-toast";
import { Card } from "@/components/ui/card";
import { motion } from "motion/react";
import { Mail, MessageSquare, CheckCircle, AlertCircle } from "lucide-react";
import axios from "axios";

type MessageHistoryEntry = {
  id: number;
  type: "email" | "whatsapp";
  timestamp: Date;
  recipient: string;
  subject?: string; // Только для email
  message: string;
  response: string;
};

export default function DashboardClient() {
  // Вызываем хуки всегда, в одном и том же порядке
  const { data: session, status } = useSession();
  const [email, setEmail] = useState("");
  const [subject, setSubject] = useState("");
  const [message, setMessage] = useState("");
  const [phone, setPhone] = useState("");
  const [whatsAppMessage, setWhatsAppMessage] = useState("");
  const [messageHistory, setMessageHistory] = useState<MessageHistoryEntry[]>(
    [],
  );
  const { toast } = useToast();

  // После вызова всех хуков можно условно рендерить контент
  if (status === "loading") {
    return null; // или покажи спиннер, если нужно
  }

  const userAccessToken = session?.user?.access;
  const generateId = () => Date.now() + Math.random();

  async function handleSendEmail() {
    if (!userAccessToken) return;
    try {
      const res = await sendEmail(userAccessToken, email, subject, message);

      toast({
        title: "Email Sent",
        description: `Response: ${JSON.stringify(res)}`,
      });

      const newEntry: MessageHistoryEntry = {
        id: generateId(),
        type: "email",
        timestamp: new Date(),
        recipient: email,
        subject,
        message,
        response: JSON.stringify(res),
      };
      setMessageHistory((prev) => [newEntry, ...prev]);

      setEmail("");
      setSubject("");
      setMessage("");
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
    } catch (error: any) {
      console.error("Error sending email:", error);
      if (axios.isAxiosError(error)) {
        console.error("Error data:", error.response?.data);
      }
      toast({
        title: "Error while sending email",
        description:
          error.response?.data?.error || error.message || "Unknown error",
        variant: "destructive",
      });
    }
  }

  async function handleSendWhatsApp() {
    if (!userAccessToken) return;
    try {
      const res = await sendWhatsApp(userAccessToken, phone, whatsAppMessage);

      toast({
        title: "WhatsApp Message Sent",
        description: `Response: ${JSON.stringify(res)}`,
      });

      const newEntry: MessageHistoryEntry = {
        id: generateId(),
        type: "whatsapp",
        timestamp: new Date(),
        recipient: phone,
        message: whatsAppMessage,
        response: JSON.stringify(res),
      };
      setMessageHistory((prev) => [newEntry, ...prev]);

      setPhone("");
      setWhatsAppMessage("");
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
    } catch (error: any) {
      console.error("Error sending WhatsApp:", error);
      if (axios.isAxiosError(error)) {
        console.error("Error data:", error.response?.data);
      }
      toast({
        title: "Error while sending WhatsApp message",
        description:
          error.response?.data?.error || error.message || "Unknown error",
        variant: "destructive",
      });
    }
  }

  return (
    <motion.div
      className="min-h-screen bg-gray-100 dark:bg-gray-900 p-8"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ duration: 0.5 }}
    >
      <div className="max-w-7xl mx-auto">
        {/* Header */}
        <header className="mb-8 flex items-center justify-between">
          <h1 className="text-3xl font-bold text-gray-800 dark:text-gray-200">
            Welcome to Dashboard page!
          </h1>
        </header>

        {/* Две колонки */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-8">
          {/* Отправка Email */}
          <Card className="p-6 shadow-lg bg-white dark:bg-gray-800">
            <div className="flex items-center mb-4">
              <Mail className="w-6 h-6 text-blue-500 mr-2" />
              <h2 className="text-xl font-semibold text-gray-700 dark:text-gray-300">
                Send Email
              </h2>
            </div>
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300">
                  Recipient Email
                </label>
                <Input
                  type="email"
                  placeholder="example@domain.com"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  required
                  className="mt-1"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300">
                  Email Subject
                </label>
                <Input
                  type="text"
                  placeholder="Subject"
                  value={subject}
                  onChange={(e) => setSubject(e.target.value)}
                  required
                  className="mt-1"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300">
                  Message
                </label>
                <textarea
                  className="mt-1 border rounded-md p-2 w-full focus:outline-none focus:ring-2 focus:ring-blue-500 dark:bg-gray-700 dark:text-gray-200"
                  placeholder="Enter the email text..."
                  value={message}
                  onChange={(e) => setMessage(e.target.value)}
                  rows={4}
                  required
                />
              </div>
              <Button
                onClick={handleSendEmail}
                className="w-full flex items-center justify-center"
              >
                <Mail className="w-4 h-4 mr-2" />
                <span>Send Email</span>
              </Button>
            </div>
          </Card>

          {/* Отправка WhatsApp */}
          <Card className="p-6 shadow-lg bg-white dark:bg-gray-800">
            <div className="flex items-center mb-4">
              <MessageSquare className="w-6 h-6 text-green-500 mr-2" />
              <h2 className="text-xl font-semibold text-gray-700 dark:text-gray-300">
                Send WhatsApp
              </h2>
            </div>
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300">
                  Phone Number
                </label>
                <Input
                  type="tel"
                  placeholder="+71234567890"
                  value={phone}
                  onChange={(e) => setPhone(e.target.value)}
                  required
                  className="mt-1"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300">
                  Message
                </label>
                <textarea
                  className="mt-1 border rounded-md p-2 w-full focus:outline-none focus:ring-2 focus:ring-green-500 dark:bg-gray-700 dark:text-gray-200"
                  placeholder="Enter the message text..."
                  value={whatsAppMessage}
                  onChange={(e) => setWhatsAppMessage(e.target.value)}
                  rows={4}
                  required
                />
              </div>
              <Button
                onClick={handleSendWhatsApp}
                className="w-full flex items-center justify-center"
              >
                <MessageSquare className="w-4 h-4 mr-2" />
                <span>Send WhatsApp</span>
              </Button>
            </div>
          </Card>
        </div>

        {/* История отправленных сообщений */}
        <Card className="p-6 shadow-lg bg-white dark:bg-gray-800">
          <div className="flex items-center mb-4">
            <CheckCircle className="w-6 h-6 text-indigo-500 mr-2" />
            <h2 className="text-xl font-semibold text-gray-700 dark:text-gray-300">
              Sent Messages History
            </h2>
          </div>
          {messageHistory.length === 0 ? (
            <p className="text-gray-600 dark:text-gray-400">
              No sent messages.
            </p>
          ) : (
            <div className="space-y-4 max-h-96 overflow-y-auto">
              {messageHistory.map((entry) => (
                <div
                  key={entry.id}
                  className="p-4 border rounded-md bg-gray-50 dark:bg-gray-700 flex flex-col md:flex-row items-start md:items-center justify-between"
                >
                  <div className="flex items-center space-x-4">
                    {entry.type === "email" ? (
                      <Mail className="w-5 h-5 text-blue-500" />
                    ) : (
                      <MessageSquare className="w-5 h-5 text-green-500" />
                    )}
                    <div>
                      <p className="text-sm font-medium text-gray-800 dark:text-gray-200">
                        {entry.type === "email" ? "Email" : "WhatsApp"}
                      </p>
                      <p className="text-sm text-gray-600 dark:text-gray-400">
                        Recipient: {entry.recipient}
                      </p>
                      {entry.type === "email" && (
                        <p className="text-sm text-gray-600 dark:text-gray-400">
                          Subject: {entry.subject}
                        </p>
                      )}
                    </div>
                  </div>
                  <div className="mt-2 md:mt-0 flex items-center space-x-2">
                    <span className="text-xs text-gray-500 dark:text-gray-400">
                      {entry.timestamp.toLocaleString()}
                    </span>
                    <span
                      className={`flex items-center text-xs font-semibold px-2 py-1 rounded ${
                        entry.response.includes("success")
                          ? "bg-green-100 text-green-800"
                          : "bg-red-100 text-red-800"
                      }`}
                    >
                      {entry.response.includes("success") ? (
                        <>
                          <CheckCircle className="w-4 h-4 mr-1" />
                          Success
                        </>
                      ) : (
                        <>
                          <AlertCircle className="w-4 h-4 mr-1" />
                          Error
                        </>
                      )}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </Card>
      </div>
    </motion.div>
  );
}
