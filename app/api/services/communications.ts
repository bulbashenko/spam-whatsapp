"use server";
import axios from "axios";

const BASE_URL = process.env.BASE_BACKEND_URL;
if (!BASE_URL) {
  throw new Error(
    "BASE_BACKEND_URL is not defined in the environment variables",
  );
}

export interface Business {
  id: number;
  name: string;
  address: string;
  phone_number: string;
  website?: string;
  category: string;
  google_maps_link: string;
  google_place_id?: string;
  social_profiles: SocialMediaProfile[];
  created_at: string;
  updated_at: string;
}

export interface SocialMediaProfile {
  id: number;
  platform: string;
  profile_url: string;
  verified: boolean;
  verification_date?: string;
  profile_data?: {
    followers?: number;
    following?: number;
    posts?: number;
    description?: string;
    [key: string]: unknown;
  };
}

export interface MessageHistory {
  id: number;
  type: "email" | "whatsapp";
  status: string;
  recipient: string;
  content: string;
  subject?: string;
  error_message?: string;
  whatsapp_message_id?: string;
  created_at: string;
  sent_at?: string;
}

export async function sendEmail(
  accessToken: string,
  to: string,
  subject: string,
  message: string,
) {
  const res = await axios.post(
    `${BASE_URL}/api/communications/email/`,
    { to, subject, message },
    {
      headers: {
        Authorization: `Bearer ${accessToken}`,
      },
    },
  );
  return res.data;
}

export async function sendWhatsApp(
  accessToken: string,
  to: string,
  message: string,
) {
  const res = await axios.post(
    `${BASE_URL}/api/communications/whatsapp/`,
    {
      to,
      message_type: "text",
      message,
    },
    {
      headers: {
        Authorization: `Bearer ${accessToken}`,
      },
    },
  );
  return res.data;
}

export async function getMessageHistory(
  accessToken: string,
  type?: "email" | "whatsapp",
  page: number = 1,
) {
  const params = new URLSearchParams();
  if (type) params.append("type", type);
  params.append("page", page.toString());

  const res = await axios.get(
    `${BASE_URL}/api/communications/history/?${params.toString()}`,
    {
      headers: {
        Authorization: `Bearer ${accessToken}`,
      },
    },
  );
  return res.data;
}

export async function getBusinesses(accessToken: string) {
  const res = await axios.get(`${BASE_URL}/api/communications/businesses/`, {
    headers: {
      Authorization: `Bearer ${accessToken}`,
    },
  });
  return res.data;
}

export async function createBusiness(
  accessToken: string,
  data: Omit<Business, "id" | "social_profiles" | "created_at" | "updated_at">,
) {
  const res = await axios.post(
    `${BASE_URL}/api/communications/businesses/`,
    data,
    {
      headers: {
        Authorization: `Bearer ${accessToken}`,
      },
    },
  );
  return res.data;
}

export async function searchBusinesses(
  accessToken: string,
  query: string,
  location: string,
) {
  const res = await axios.post(
    `${BASE_URL}/api/communications/businesses/search/`,
    { query, location },
    {
      headers: {
        Authorization: `Bearer ${accessToken}`,
      },
    },
  );

  // The backend returns { status: "success", businesses: [...] } or { status: "error", error: "..." }
  if (res.data.status === "error") {
    throw new Error(res.data.error);
  }

  return res.data.businesses || [];
}

export async function sendBulkMessage(
  accessToken: string,
  type: "email" | "whatsapp",
  recipients: string[],
  content: string,
  subject?: string,
) {
  const res = await axios.post(
    `${BASE_URL}/api/communications/bulk/`,
    { type, recipients, content, subject },
    {
      headers: {
        Authorization: `Bearer ${accessToken}`,
      },
    },
  );
  return res.data;
}
