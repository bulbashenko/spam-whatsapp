// app/api/services/auth.ts
"use server";
import axios, { AxiosError } from "axios";

const BASE_URL = process.env.BASE_BACKEND_URL;

export interface AuthResponse {
  id: string;
  access: string;
  refresh: string;
  email: string;
}

export async function authLogin(email: string, password: string) {
  try {
    // Тип ожидаемого ответа (можно расширить, если у вас ещё какие-то поля)
    interface LoginResponse {
      success: boolean;
      data: {
        refresh: string;
        access: string;
        userId?: number; // если возвращаете userId, может быть любой тип
      };
    }

    // Делаем POST-запрос к вашему серверу
    const res = await axios.post<LoginResponse>(`${BASE_URL}/api/auth/login/`, {
      email,
      password,
    });

    // Если бэкенд вернул success: true, оттуда берём access/refresh
    if (res.data.success && res.data.data.access && res.data.data.refresh) {
      // id приводим к string, т.к. NextAuth ожидает, что поле id будет строкой
      return {
        // Если бэкенд возвращает userId = 123, делаем String(123) = '123'
        id: String(res.data.data.userId ?? email),
        access: res.data.data.access,
        refresh: res.data.data.refresh,
        email, // Либо возьмите из бэкенда, если он возвращает тоже
      };
    }

    // Если success=false или нет токенов — авторизация не удалась
    return null;
  } catch (error) {
    const err = error as AxiosError;
    console.error("authLogin error:", err.response?.data || err.message);
    // Возвращаем null, чтобы NextAuth понял: логин неуспешен
    return null;
  }
}

/**
 * Регистрация (POST /api/auth/register/).
 * Возвращает ответ бэкенда целиком (success, data, ...)
 * Если нужно — допилите логику и тайпинги.
 */
export async function authRegister(email: string, password: string) {
  try {
    const res = await axios.post(`${BASE_URL}/api/auth/register/`, {
      email,
      password,
    });
    // Ожидаем что-то вроде:
    // {
    //   "success": true,
    //   "data": {
    //     "refresh": "...",
    //     "access": "..."
    //   }
    // }
    return res.data;
  } catch (error) {
    const err = error as AxiosError;
    console.error("authRegister error:", err.response?.data || err.message);
    // Пробрасываем ошибку, чтобы её смогли отловить в форме
    throw error;
  }
}

/**
 * Логаут (POST /api/auth/logout/).
 * Деактивирует refresh-токен на бэкенде.
 */
export async function authLogout(refreshToken: string, accessToken: string) {
  try {
    const res = await axios.post(
      `${BASE_URL}/api/auth/logout/`,
      {
        refresh: refreshToken,
      },
      {
        headers: {
          Authorization: `Bearer ${accessToken}`,
        },
      },
    );
    return res.data;
  } catch (error) {
    const err = error as AxiosError;
    console.error("authLogout error:", err.response?.data || err.message);
    throw error;
  }
}

export async function authLoginFacebook(
  facebookAccessToken: string,
  redirect_uri: string,
) {
  try {
    // Тип ожидаемого ответа
    interface FacebookLoginResponse {
      success: boolean;
      data: {
        refresh: string;
        access: string;
        userId?: number;
        email?: string;
      };
    }

    // Делаем POST-запрос к вашему серверу с токеном и redirect_uri
    const res = await axios.post<FacebookLoginResponse>(
      `${BASE_URL}/api/auth/login/facebook/`,
      {
        code: facebookAccessToken, // Assuming your backend expects the Facebook access token as 'code'
        redirect_uri,
      },
    );

    // Если бэкенд вернул success: true, возвращаем необходимые данные
    if (res.data.success && res.data.data.access && res.data.data.refresh) {
      return {
        id: String(res.data.data.userId ?? "facebook_user"),
        access: res.data.data.access,
        refresh: res.data.data.refresh,
        email: res.data.data.email ?? "facebook_user@example.com",
      };
    }

    // Если успех не подтверждён, возвращаем null
    return null;
  } catch (error) {
    const err = error as AxiosError;
    console.error(
      "authLoginFacebook error:",
      err.response?.data || err.message,
    );
    return null;
  }
}
