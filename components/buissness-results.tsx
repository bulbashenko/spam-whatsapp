"use client";

import { useEffect, useState, useCallback } from "react";
import { useSession } from "next-auth/react";
import { useToast } from "@/hooks/use-toast";
import { redirect } from "next/navigation";
import { motion } from "motion/react";
import {
  Business,
  getBusinesses,
  createBusiness,
  searchBusinesses,
} from "@/app/api/services/communications";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Search, PlusCircle, XCircle, Building, MapPin } from "lucide-react";

export default function BusinessesPage() {
  const { data: session, status } = useSession();
  const { toast } = useToast();

  const [businesses, setBusinesses] = useState<Business[]>([]);
  const [loading, setLoading] = useState(false);

  const [searchQuery, setSearchQuery] = useState("");
  const [searchLocation, setSearchLocation] = useState("");

  const [showAddForm, setShowAddForm] = useState(false);
  const [newBusiness, setNewBusiness] = useState({
    name: "",
    address: "",
    phone_number: "",
    website: "",
    category: "",
    google_maps_link: "",
  });

  console.log("===== BusinessesPage RENDER =====");
  console.log("session =", session);
  console.log("status =", status);

  // Если пользователь не аутентифицирован — редиректим
  useEffect(() => {
    if (status === "unauthenticated") {
      console.log("Пользователь не аутентифицирован, редиректим на /login");
      redirect("/login");
    }
  }, [status]);

  // Загрузка всех бизнесов
  const loadBusinesses = useCallback(async () => {
    try {
      setLoading(true);
      console.log("=== loadBusinesses ===");
      console.log("accessToken =", session?.user?.access);

      const data = await getBusinesses(session!.user.access as string);
      setBusinesses(data);
      console.log("Загрузили businesses:", data);
    } catch (error) {
      console.error("Ошибка при загрузке businesses:", error);
      toast({
        title: "Error",
        description: "Failed to load businesses",
        variant: "destructive",
      });
    } finally {
      setLoading(false);
    }
  }, [session, toast]);

  // При монтировании и при наличии токена грузим бизнесы
  useEffect(() => {
    if (status === "authenticated" && session?.user?.access) {
      console.log(
        "Статус: authenticated. Сессия есть. Пытаемся подгрузить businesses...",
      );
      loadBusinesses();
    } else {
      console.log(
        "Либо статус не authenticated, либо нет session?.user?.access:",
        session?.user?.access,
      );
    }
  }, [status, session, loadBusinesses]);

  // Обработка поиска
  async function handleSearch() {
    console.log("=== Нажали на Search ===");
    console.log("session?.user.access =", session?.user?.access);
    console.log(
      "searchQuery =",
      searchQuery,
      "| searchLocation =",
      searchLocation,
    );

    if (!searchQuery || !searchLocation) {
      console.log("Не заданы searchQuery или searchLocation!");
      toast({
        title: "Validation Error",
        description: "Both search query and location are required",
        variant: "destructive",
      });
      return;
    }

    try {
      setLoading(true);
      console.log("Отправляем запрос searchBusinesses...");
      const found = await searchBusinesses(
        session!.user.access as string,
        searchQuery,
        searchLocation,
      );
      console.log("searchBusinesses вернул:", found);
      setBusinesses(found);

      if (found.length === 0) {
        toast({
          title: "No Results",
          description: "No businesses found for your search criteria",
        });
      } else {
        toast({
          title: "Search Completed",
          description: `Found ${found.length} businesses`,
        });
      }
    } catch (error) {
      console.error("Ошибка в searchBusinesses:", error);
      toast({
        title: "Search Error",
        description:
          error instanceof Error
            ? error.message
            : "Failed to search businesses",
        variant: "destructive",
      });
    } finally {
      setLoading(false);
    }
  }

  // Обработка добавления нового бизнеса
  async function handleAddBusiness(e: React.FormEvent) {
    e.preventDefault();
    console.log("=== handleAddBusiness ===");
    console.log("Новый бизнес:", newBusiness);
    console.log("session?.user.access =", session?.user?.access);

    if (
      !newBusiness.name ||
      !newBusiness.address ||
      !newBusiness.phone_number
    ) {
      console.log(
        "Не заполнены обязательные поля: name, address, phone_number",
      );
      toast({
        title: "Validation Error",
        description: "Name, address and phone number are required",
        variant: "destructive",
      });
      return;
    }

    try {
      setLoading(true);
      console.log("createBusiness: отправляем запрос...");
      await createBusiness(session!.user.access as string, newBusiness);
      toast({
        title: "Success",
        description: "Business added successfully",
      });

      setShowAddForm(false);
      setNewBusiness({
        name: "",
        address: "",
        phone_number: "",
        website: "",
        category: "",
        google_maps_link: "",
      });

      // Перезагружаем список
      await loadBusinesses();
    } catch (error) {
      console.error("Ошибка при создании бизнеса:", error);
      toast({
        title: "Error",
        description: "Failed to add business",
        variant: "destructive",
      });
    } finally {
      setLoading(false);
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
        {/* Заголовок и кнопка "Add Business" */}
        <header className="mb-8 flex items-center justify-between">
          <h1 className="text-3xl font-bold text-gray-800 dark:text-gray-200">
            Businesses
          </h1>
          <Button
            onClick={() => setShowAddForm(!showAddForm)}
            className="flex items-center space-x-2"
          >
            {showAddForm ? (
              <>
                <XCircle className="w-4 h-4" />
                <span>Cancel</span>
              </>
            ) : (
              <>
                <PlusCircle className="w-4 h-4" />
                <span>Add Business</span>
              </>
            )}
          </Button>
        </header>

        {/* Карточка поиска */}
        <Card className="p-6 mb-8 shadow-lg bg-white dark:bg-gray-800">
          <div className="flex items-center mb-4 space-x-2">
            <Search className="w-5 h-5 text-blue-500" />
            <h2 className="text-xl font-semibold text-gray-700 dark:text-gray-300">
              Search Businesses
            </h2>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300">
                Search Query
              </label>
              <Input
                placeholder='e.g. "coffee shop"'
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="mt-1"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300">
                Location
              </label>
              <Input
                placeholder='e.g. "New York"'
                value={searchLocation}
                onChange={(e) => setSearchLocation(e.target.value)}
                className="mt-1"
              />
            </div>
          </div>
          <Button
            onClick={handleSearch}
            disabled={loading}
            className="mt-2 flex items-center space-x-2"
          >
            <Search className="w-4 h-4" />
            <span>Search</span>
          </Button>
        </Card>

        {/* Форма добавления нового бизнеса */}
        {showAddForm && (
          <Card className="p-6 mb-8 shadow-lg bg-white dark:bg-gray-800">
            <div className="flex items-center mb-4 space-x-2">
              <PlusCircle className="w-5 h-5 text-green-500" />
              <h2 className="text-xl font-semibold text-gray-700 dark:text-gray-300">
                Add New Business
              </h2>
            </div>
            <form onSubmit={handleAddBusiness} className="space-y-4">
              {/* Name */}
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300">
                  Business Name *
                </label>
                <Input
                  placeholder="Business Name"
                  value={newBusiness.name}
                  onChange={(e) =>
                    setNewBusiness({ ...newBusiness, name: e.target.value })
                  }
                  className="mt-1"
                />
              </div>
              {/* Address */}
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300">
                  Address *
                </label>
                <Input
                  placeholder="Street 123, City, etc."
                  value={newBusiness.address}
                  onChange={(e) =>
                    setNewBusiness({ ...newBusiness, address: e.target.value })
                  }
                  className="mt-1"
                />
              </div>
              {/* Phone Number */}
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300">
                  Phone Number *
                </label>
                <Input
                  placeholder="+1234567890"
                  value={newBusiness.phone_number}
                  onChange={(e) =>
                    setNewBusiness({
                      ...newBusiness,
                      phone_number: e.target.value,
                    })
                  }
                  className="mt-1"
                />
              </div>
              {/* Website */}
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300">
                  Website
                </label>
                <Input
                  placeholder="https://example.com"
                  value={newBusiness.website}
                  onChange={(e) =>
                    setNewBusiness({ ...newBusiness, website: e.target.value })
                  }
                  className="mt-1"
                />
              </div>
              {/* Category */}
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300">
                  Category
                </label>
                <Input
                  placeholder="e.g. Cafe, Store, etc."
                  value={newBusiness.category}
                  onChange={(e) =>
                    setNewBusiness({
                      ...newBusiness,
                      category: e.target.value,
                    })
                  }
                  className="mt-1"
                />
              </div>
              {/* Google Maps Link */}
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300">
                  Google Maps Link
                </label>
                <Input
                  placeholder="https://maps.google.com/..."
                  value={newBusiness.google_maps_link}
                  onChange={(e) =>
                    setNewBusiness({
                      ...newBusiness,
                      google_maps_link: e.target.value,
                    })
                  }
                  className="mt-1"
                />
              </div>
              <Button
                type="submit"
                disabled={loading}
                className="flex items-center space-x-2"
              >
                <PlusCircle className="w-4 h-4" />
                <span>Add Business</span>
              </Button>
            </form>
          </Card>
        )}

        {/* Отображение списка бизнесов или индикатора загрузки */}
        <BusinessResults businesses={businesses} loading={loading} />
      </div>
    </motion.div>
  );
}

// Новый компонент для отображения результатов
function BusinessResults({
  businesses,
  loading,
}: {
  businesses: Business[];
  loading: boolean;
}) {
  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[200px] bg-gray-100 dark:bg-gray-900">
        <p className="text-xl text-gray-700 dark:text-gray-300">Loading...</p>
      </div>
    );
  }

  if (businesses.length === 0) {
    return (
      <div className="text-center text-gray-700 dark:text-gray-300">
        <p>No businesses found.</p>
      </div>
    );
  }

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
      {businesses.map((business) => (
        <Card
          key={business.id}
          className="p-6 shadow-lg bg-white dark:bg-gray-800"
        >
          <div className="flex items-center space-x-2 mb-2">
            <Building className="w-5 h-5 text-indigo-500" />
            <h3 className="text-lg font-semibold text-gray-800 dark:text-gray-200">
              {business.name}
            </h3>
          </div>
          <div className="mb-1 text-sm text-gray-600 dark:text-gray-400 flex items-center space-x-1">
            <MapPin className="w-4 h-4" />
            <span>{business.address}</span>
          </div>
          <p className="text-sm text-gray-600 dark:text-gray-400 mb-1">
            Phone: {business.phone_number}
          </p>
          {business.website && (
            <p className="text-sm text-blue-600 mb-1 underline">
              <a
                href={business.website}
                target="_blank"
                rel="noopener noreferrer"
              >
                Website
              </a>
            </p>
          )}
          {business.category && (
            <p className="text-sm text-gray-600 dark:text-gray-400 mb-1">
              Category: {business.category}
            </p>
          )}
          {business.social_profiles.length > 0 && (
            <div className="mt-2">
              <p className="text-sm font-semibold text-gray-700 dark:text-gray-300">
                Social Profiles:
              </p>
              <div className="flex flex-wrap mt-1 space-x-2">
                {business.social_profiles.map((profile) => (
                  <a
                    key={profile.id}
                    href={profile.profile_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-sm text-blue-500 underline"
                  >
                    {profile.platform}
                  </a>
                ))}
              </div>
            </div>
          )}
        </Card>
      ))}
    </div>
  );
}
